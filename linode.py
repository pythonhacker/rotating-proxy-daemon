import os
import random
import functools
from base import ProxyRotator
from utils import randpass

class LinodeCommand(object):
    """ Class encapsulating linode CLI commands """

    def __init__(self, binary='linode', verbose=False, config=None):
        self.binary = binary
        self.verbose = verbose
        self.cmd_template = {'create': 'create -d %d -p %d -o %d -i %d -l %s -r %s',
                             'delete': 'delete -l %d',
                             'list_proxies': 'find -g %s -s %s' % (config.group, config.proxylb),
                             'info': 'info -l %d',
                             'update': 'update -l %d -L %s -g %s'
                             }
        # Dynamically create command methods
        self.dyn_create()
                             
    def _run(self, command, *args):
        """ Run a command and return the output """

        template = self.cmd_template.get(command)
        if template == None:
            print 'No such command configured =>',command
            return -1

        cmd = ' '.join((self.binary, template % args))
        if self.verbose: print 'Command is',cmd
        return os.popen(cmd).read()

    def dyn_create(self):
        """ Dynamically create linode methods """

        for cmd in self.cmd_template:
            method_name = cmd
            method = functools.partial(self._run, cmd)
            if self.verbose: print 'Dyn-creating method',method_name,'...'
            setattr(self, method_name, method)
            
    def get_label(self, linode_id):
        """ Return the label, given the linode id """

        data = self.info(linode_id)
        return data.split('\n')[0].split(':')[-1].strip()

    def get_proxies(self):
        """ Return all proxies as a list """

        return self.list_proxies().strip().split('\n')
    
class LinodeProxyRotator(ProxyRotator):
    """ Linode VPS implementation of ProxyRotator """

    def __init__(self, cfg='proxy.conf', test_mode=False, rotate=False, region=None):
        super(LinodeProxyRotator, self).__init__(cfg, test_mode, rotate, region)
        # Linode creation class
        self.linode_command = LinodeCommand(verbose=True, config=self.config)
        self.vps_command = self.linode_command
        
    def get_instance_label(self, instance_id):
        """ Return instance label given instance id """
        return self.linode_command.get_label(instance_id)

    def delete_instance(self, instance_id):
        """ Delete instance by id """
        return self.linode_command.delete(proxy_out_id)
                    
    def make_new_instance(self, region, test=False, verbose=False):
        """ Make a new instance in the given region """

        # If calling as test, make up an ip
        if test:
            return '.'.join(map(lambda x: str(random.randrange(20, 100)), range(4))), random.randrange(10000,
                                                                                                       50000)
                
        tup = (region,
               self.config.plan_id,
               self.config.os_id,
               self.config.image_id,
               'proxy_disk',
               randpass())
        
        print 'Making new linode in region',region,'...'        
        data = self.linode_command.create(*tup)
        
        # data = os.popen(cmd).read()
        if verbose:
            print data
        # The IP is the last line of the command
        ip = data.strip().split('\n')[-1].strip().split()[-1].strip()
        # Proxy ID
        pid = data.strip().split('\n')[-3].strip().split()[-1].strip()
        print 'I.P address of new linode is',ip
        print 'ID of new linode is',pid
        # Post process the host
        print 'Post-processing',ip,'...'
        self.post_process(ip)

    def update_instance(self, instance_id, label, group=None):
        """ Update meta-data for a new instance """

        # Updates label (name) and group information
        ret = self.linode_command.update(int(instance_id),
                                         label,
                                         group)
        return ret

    
    def drop(self):
        """ Drop all the proxies in current configuration (except the LB) """

        print 'Dropping all proxies ...'
        proxies = self.linode_command.get_proxies()

        for item in proxies:
            if item.strip() == "": continue
            ip,dc,lid,si,so = item.split(',')
            print '\tDropping linode',lid,'with IP',ip,'from dc',dc,'...'
            self.linode_command.delete(int(lid))

