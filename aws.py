import random
import boto3
from base import ProxyRotator

class AWSCommand(object):
    '''Class encapsulating the aws ec2 API'''

    def __init__(self, config=None):
        self.ec2 = boto3.resource('ec2')
        self.config = config

    def create_ec2(self, **params):
        return self.ec2.create_instances(MaxCount=1, MinCount=1, **params)[0]

    def get_proxies(self):
        proxies = []
        filters=[
            {'Name':'image-id', 'Values':[self.config.aws_image_id]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
        for instance in self.ec2.instances.filter(Filters=filters):
            proxies.append(','.join([instance.public_ip_address, '0', instance.id,'0','0']))
        return proxies

    def delete_ec2(self, instance_id):
        instance = self.ec2.Instance(instance_id)
        instance.terminate()
        instance.wait_until_terminated()


class AwsProxyRotator(ProxyRotator):
    """ AWS implementation of ProxyRotator """

    def __init__(self, cfg='proxy.conf', test_mode=False, rotate=False, region=None):
        super(AwsProxyRotator, self).__init__(cfg, test_mode, rotate, region)        
        #AWS resource manager
        self.aws_command = AWSCommand(config=self.config)
        self.vps_command = self.aws_command
        
    def delete_instance(self, instance_id):
        """ Delete instance by id """
        return self.aws_command.delete_ec2(instance_id)
    
    def make_new_instance(self, region=None, test=False, verbose=False):
        # If calling as test, make up an ip
        if test:
            return '.'.join(map(lambda x: str(random.randrange(20, 100)), range(4))), random.randrange(10000,
                                                                                                       50000)
        params = dict(ImageId=self.config.aws_image_id,
                      InstanceType=self.config.aws_instance_type,
                      KeyName=self.config.aws_key_name,
                      SecurityGroupIds=self.config.aws_security_groups,
                      SubnetId=self.config.aws_subnet_id ,
                      DryRun=True)

        print 'Making new ec2...'
        ec2_instance = self.aws_command.create_ec2(**params)
        ec2_instance.wait_until_running()
        time.sleep(10)

        ip = ec2_instance.public_ip_address
        pid = ec2_instance.id

        # Post process the host
        print 'Post-processing',ip,'...'
        self.post_process(ip)

        return ip, pid 

    def drop(self):
        """ Drop all instances in current configuration (except the LB) """

        print 'Dropping all proxies ...'
        proxies = self.aws_command.get_proxies()

        for item in proxies:
            ip,_,instance_id = item.split(',')
            print '\tDropping ec2',instance_id,'with IP',ip,'...'
            self.aws_command.delete_ec2(instance_id)

