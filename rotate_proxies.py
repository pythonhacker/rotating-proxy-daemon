"""
Script to auto-rotate and configure Linodes as squid proxies.

"""

import argparse
import os
import sys

def process_args(rotator, args):

    if args.test:
        print 'Testing the daemon'
        rotator.test()
        sys.exit(0)
        
    if args.add != 0:
        print 'Adding new set of',args.num,'linode proxies ...'
        rotator.provision(count = int(args.num), add=True)
        sys.exit(0)
        
    if args.provision != 0:
        print 'Provisioning fresh set of',args.num,'linode proxies ...'
        rotator.provision(count = int(args.num))
        sys.exit(0)
        
    if args.create:
        print 'Creating new linode...'
        rotator.create(int(args.region))
        sys.exit(0)

    if args.drop:
        print 'Dropping current proxies ...'
        rotator.drop()
        sys.exit(0)
        
    if args.writeconfig:
        # Load current proxies config and write proxies.list file
        rotator.write_proxies()
        print 'Saved current proxy configuration to proxies.list'
        sys.exit(0)

    if args.writelbconfig:
        # Load current proxies config and write proxies.list file
        rotator.config.write_lb_config()
        print 'Wrote HAProxy configuration'
        sys.exit(0)

        
    if args.stop or args.restart:
        pidfile = 'rotator.pid'
        if os.path.isfile(pidfile):
            print 'Stopping proxy rotator daemon ...',
            # Signal the running daemon with SIGTERM
            try:
                os.kill(int(open(pidfile).read().strip()), signal.SIGTERM)
                print 'stopped.'
            except OSError, e:
                print e
                print 'Unable to stop, possibly daemon not running.'                

        if args.restart:
            print 'Starting...'
            os.system('python rotate_proxies.py')
            
        sys.exit(1) 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='rotate_proxies')
    parser.add_argument('-C','--conf',help='Use the given configuration file', default='proxy.conf')    
    parser.add_argument('-s','--stop',help='Stop the currently running daemon', action='store_true')
    parser.add_argument('-t','--test',help='Run the test function to test the daemon', action='store_true')
    parser.add_argument('-c','--create',help='Create a proxy linode', action='store_true',default=False)
    parser.add_argument('-r','--region',help='Specify a region when creating a linode', default=3, type=int)
    parser.add_argument('-R','--rotate',help='Rotate a node immediately and go to sleep', default=False,
                        action='store_true')
    parser.add_argument('-D','--drop',help='Drop the current configuration of proxies (except LB)',
                        default=False,action='store_true')
    parser.add_argument('-P','--provision',help='Provision a fresh set of proxy linodes',default=False,
                        action='store_true')
    parser.add_argument('-A','--add',help='Add a new set of linodes to existing set',default=False,
                        action='store_true')    
    parser.add_argument('-N','--num',help='Number of new linodes to provision or add (use with -P or -A)',type=int,
                        default=10)
    
    parser.add_argument('-w','--writeconfig',help='Load current Linode proxies configuration and write a fresh proxies.list config file', action='store_true')
    parser.add_argument('-W','--writelbconfig',help='Load current Linode proxies configuration and write a fresh HAProxy config to /etc/haproxy/haproxy.cfg', action='store_true')
    parser.add_argument('--restart',help='Restart the daemon',action='store_true')
    parser.add_argument('-T','--target',help='Target VPS platform (linode, aws)',default='linode')
        
    args = parser.parse_args()
    # print args

    if args.target == 'linode':
        linode = __import__('linode')
        rotator = linode.LinodeProxyRotator(cfg=args.conf,
                                            test_mode = args.test,
                                            rotate=args.rotate)
    else:
        aws = __import__('aws')
        rotator = aws.AwsProxyRotator(cfg=args.conf,
                                      test_mode = args.test,
                                      rotate=args.rotate)


    process_args(rotator, args)
    rotator.run()
    
