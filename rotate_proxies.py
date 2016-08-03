"""
Script to auto-rotate and configure Linodes as squid proxies.

"""

import argparse
import os
import sys
import time
import random
import collections
import operator
import uuid
import threading
import signal
import json
import email_report

from utils import daemonize, randpass, enum, LinodeCommand

# Rotation Policies
Policy = enum('ROTATION_RANDOM',
              # Least recently used
              'ROTATION_LRU',
              # Switch to another region
              'ROTATION_NEW_REGION',
              # LRU + New region
              'ROTATION_LRU_NEW_REGION')

email_config = {'from_email': 'noreply@<domain>',
                'to_email': ['proxies@<domain>'],
                "send_email": True,
                "email_subject": "Proxy switch report: %s from %s"
                }

email_template = """
Hi there!

I just switched a proxy node in the proxy infrastructure.
Details are below.

Out: %(label)s, %(proxy_out)s
In: %(label)s, %(proxy_in)s
Region: %(region)s

Have a good day.

-- Proxy Rotator Daemon

"""

class ProxyConfig(object):
    """ Class representing configuration of crawler proxy infrastructure """

    def __init__(self, cfg='proxy.conf'):
        """ Initialize proxy config from the config file """

        self.parse_config(cfg)
        # This is a file with each line of the form
        # IPV4 address, datacenter code, linode-id, switch_in timestamp, switch_out timestamp
        # E.g: 45.79.91.191, 3, 1446731065, 144673390
        try:
            proxies = map(lambda x: x.strip().split(','), open(self.proxylist).readlines())
            # Proxy IP to (switch_in, switch_out) timestamp mappings
            self.proxy_dict = {}
            # Proxy IP to enabled mapping
            self.proxy_state = {}
            self.process_proxies(proxies)
        except (OSError, IOError), e:
            print e
            sys.exit("Fatal error, proxy list input file " + self.proxylist + " not found!")

        try:
            self.proxy_template = open(self.lb_template).read()
        except (OSError, IOError), e:
            print e
            sys.exit("Fatal error, template config input file " + template_file + " not found!")

    def parse_config(self, cfg):
        """ Parse the configuration file and load config """

        self.config = json.load(open(cfg))
        for key,value in self.config.items():
            # Set attribute locally
            setattr(self, key, value)

        # Do some further processing
        self.frequency = float(self.frequency)*3600.0
        self.policy = eval('Policy.' + self.policy)
        
    def get_proxy_ips(self):
        """ Return all proxy IP addresses as a list """

        return self.proxy_state.keys()

    def get_active_proxies(self):
        """ Return a list of all active proxies as a list """

        return map(self.proxy_dict.get, filter(self.proxy_state.get, self.proxy_state.keys()))
        
    def process_proxies(self, proxies):
        """ Process the proxy information to create internal dictionaries """

        # Prepare the proxy region dict
        for proxy_ip, region, proxy_id, switch_in, switch_out in proxies:
            # If switch_in ==0: put current time
            if int(float(switch_in))==0:
                switch_in = int(time.time())
            if int(float(switch_out))==0:
                switch_out = int(time.time())
                
            self.proxy_dict[proxy_ip] = [proxy_ip, int(region), int(proxy_id), int(float(switch_in)), int(float(switch_out))]
            self.proxy_state[proxy_ip] = True

        print 'Processed',len(self.proxy_state),'proxies.'

    def get_proxy_for_rotation(self,
                               use_random=False,
                               least_used=False,
                               region_switch=False,
                               input_region=3):
        """ Return a proxy IP address for rotation using the given settings. The
        returned proxy will be replaced with a new proxy.

        @use_random - Means returns a random proxy from the current active list
        @least_used - Returns a proxy IP which is the oldest switched out one
        so we keep the switching more or less democratic.
        @region_switch - Returns a proxy which belongs to a different region
        from the new proxy.
        @input_region - The region of the new proxy node - defaults to Fremont, CA.
        
        Note that if use_random is set to true, the other parameters are ignored.
        
        """

        active_proxies = self.get_active_proxies()
        print 'Active proxies =>',active_proxies
        
        if use_random:
            # Pick a random proxy IP
            proxy = random.choice(active_proxies)
            print 'Returning proxy =>',proxy
            proxy_ip = proxy[0]
            
            # Remove it from every data structure
            self.switch_out_proxy(proxy_ip)
            return proxy

        if least_used:
            # Pick the oldest switched out proxy i.e one
            # with smallest switched out value
            proxies_used = sorted(active_proxies,
                                  key=operator.itemgetter(-1))

            print 'Proxies used =>',proxies_used
            
            if region_switch:
                # Find the one with a different region from input
                for proxy, reg, pi, si, so in proxies_used:
                    if reg != input_region:
                        print 'Returning proxy',proxy,'from region',reg
                        self.switch_out_proxy(proxy)                        
                        return proxy

            # If all regions are already in use, pick the last used
            # proxy anyway
            return proxies_used[0][0]
            
        if region_switch:
            # Pick a random proxy not in the input region
            proxies = active_proxies
            random.shuffle(proxies)

            for proxy, reg, pi, si, so in proxies:
                if reg != input_region:
                    print 'Returning proxy',proxy,'from region',reg
                    self.switch_out_proxy(proxy)                    
                    return proxy
            
    def switch_out_proxy(self, proxy):
        """ Switch out a given proxy IP """

        # Disable it
        self.proxy_state[proxy] = False
        # Mark its switched out timestamp
        self.proxy_dict[proxy][-1] = int(time.time())

    def switch_in_proxy(self, proxy, proxy_id, region):
        """ Switch in a given proxy IP """

        # Mark its switched out timestamp
        self.proxy_dict[proxy] = [proxy, int(region), int(proxy_id), int(time.time()), int(time.time())]
        # Enable it
        self.proxy_state[proxy] = True     

    def get_active_regions(self):
        """ Return unique regions for which proxies are active """

        regions = set()
        for proxy,region,pi,si,so in self.proxy_dict.values():
            if self.proxy_state[proxy]:
                regions.add(region)

        return list(regions)
        
    def write(self, disabled=False):
        """ Write current state to an output file """

        lines = []
        for proxy, reg, pi, si, so in self.proxy_dict.values():
            if disabled or self.proxy_state[proxy]:
                lines.append('%s,%s,%s,%s,%s\n' % (proxy, str(reg), str(pi), str(int(si)), str(int(so))))

        open(self.proxylist,'w').writelines(lines)

    def write_lb_config(self, disabled=False, test=False):
        """ Write current proxy configuration into the load balancer config """

        lines, idx = [], 1
        for proxy, reg, pi, si, so in self.proxy_dict.values():
            if self.proxy_state[proxy]:
                lines.append('\tserver  squid%d %s:8123 check inter 10000 rise 2 fall 5' % (idx, proxy))
                idx += 1

        squid_config = "\n".join(lines)
        content = self.proxy_template % locals()
        # Write to temp file
        tmpfile = '/tmp/.haproxy.cfg'
        open(tmpfile,'w').write(content)

        # If running in test mode, don't do this!
        if not test:
            # Run as sudo
            cmd = 'sudo cp %s %s; rm -f %s' % (tmpfile, self.lb_config, tmpfile)
            os.system(cmd)

        self.reload_lb()
        return True

    def reload_lb(self):
        """ Reload the HAProxy load balancer """

        return (os.system(self.lb_restart) == 0)

    def get_proxy_id(self, proxy):
        """ Given proxy return its id """

        return self.proxy_dict[proxy][2]
    
class ProxyRotator(object):
    """ Proxy rotation, provisioning & re-configuration with linode nodes """

    def __init__(self, cfg='proxy.conf', test_mode=False, rotate=False, region=None):
        self.config = ProxyConfig(cfg=cfg)        
        print 'Frequency set to',self.config.frequency,'seconds.'
        # Test mode ?
        self.test_mode = test_mode
        # Event object
        self.alarm = threading.Event()
        # Clear the event
        self.alarm.clear()
        # Heartbeat file
        self.hbf = '.heartbeat'
        # Linode creation class
        self.linode_cmd = LinodeCommand(verbose=True)
        # If rotate is set, rotate before going to sleep
        if rotate:
            print 'Rotating a node'
            self.rotate(region=region)
            
        signal.signal(signal.SIGTERM, self.sighandler)
        signal.signal(signal.SIGUSR1, self.sighandler)      
            
    def pick_region(self):
        """ Pick the region for the new node """

        # Try and pick a region not present in the
        # current list of nodes
        regions = self.config.get_active_regions()
        # Shuffle current regions
        random.shuffle(self.config.region_ids)
        
        for reg in self.config.region_ids:
            if reg not in regions:
                return reg
            
        # All regions already present ? Pick a random one.
        return random.choice(self.config.region_ids)

    def make_new_linode(self, region, test=False, verbose=False):
        """ Make a new linode in the given region """

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
        data = self.linode_cmd.linode_create(*tup)
        
        # data = os.popen(cmd).read()
        if verbose:
            print data
        # The IP is the last line of the command
        ip = data.strip().split('\n')[-1].strip().split()[-1].strip()
        # Proxy ID
        pid = data.strip().split('\n')[-3].strip().split()[-1].strip()
        print 'I.P address of new linode is',ip
        print 'ID of new linode is',pid
        return ip, pid

    def rotate(self, region=None):
        """ Rotate the configuration to a new node """

        proxy_out_label = None
        # Pick the data-center
        if region == None:
            print 'Picking a region ...'
            region = self.pick_region()
        else:
            print 'Using supplied region',region,'...'
            
        # Switch in the new linode from this region
        new_proxy, proxy_id = self.make_new_linode(region)
        # Rotate another node
        if self.config.policy == Policy.ROTATION_RANDOM:
            proxy_out = self.config.get_proxy_for_rotation(use_random=True, input_region=region)
        elif self.config.policy == Policy.ROTATION_NEW_REGION:
            proxy_out = self.config.get_proxy_for_rotation(region_switch=True, input_region=region)
        elif self.config.policy == Policy.ROTATION_LRU:
            proxy_out = self.config.get_proxy_for_rotation(least_used=True, input_region=region)
        elif self.config.policy == Policy.ROTATION_LRU_NEW_REGION:
            proxy_out = self.config.get_proxy_for_rotation(least_used=True, region_switch=True,
                                                           input_region=region)
            
        # Switch in the new proxy
        self.config.switch_in_proxy(new_proxy, proxy_id, region)
        print 'Switched in new proxy',new_proxy
        # Write configuration
        self.config.write()
        print 'Wrote new configuration.'
        # Write new HAProxy LB template and reload ha proxy
        ret1 = self.config.write_lb_config()
        ret2 = self.config.reload_lb()
        if ret1 and ret2:
            if proxy_out != None:
                print 'Switched out proxy',proxy_out
                proxy_out_id = int(self.config.get_proxy_id(proxy_out))
                
                if proxy_out_id != 0:
                    proxy_out_label = self.linode_cmd.get_label(proxy_out_id)
                    print 'Removing switched out linode',proxy_out_id
                    self.linode_cmd.linode_delete(proxy_out_id)
                else:
                    'Proxy id is 0, not removing linode',proxy_out
        else:
            print 'Error - Did not switch out proxy as there was a problem in writing/restarting LB'


        if proxy_out_label != None:
            # Get its label and assign it to the new linode
            print 'Assigning label',proxy_out_label,'to new linode',proxy_id
            time.sleep(5)
            self.linode_cmd.linode_update(int(proxy_id),
                                          proxy_out_label,
                                          self.config.group)

        # Post process the host
        print 'Post-processing',new_proxy,'...'
        self.post_process(new_proxy)
        self.send_email(proxy_out, proxy_out_label, new_proxy, region)

    def send_email(self, proxy_out, label, proxy_in, region):
        """ Send email upon switching of a proxy """

        print 'Sending email...'
        content = email_template % locals()
        email_report.email_report(email_config, "%s", content)
                   
    def post_process(self, ip):
        """ Post-process a switched-in host """

        cmd="fab process_proxy_host -H %s -u ubuntu" % ip
        os.system(cmd)
        
    def alive(self):
        """ Return whether I should be alive """

        return os.path.isfile(self.hbf)

    def create(self, region=3):
        """ Create a new linode for testing """

        print 'Creating new linode in region',region,'...'
        new_proxy = self.make_new_linode(region, verbose=True)

    def drop(self):
        """ Drop all the proxies in current configuration (except the LB) """

        print 'Dropping all proxies ...'
        proxies = rotator.linode_cmd.linode_list_proxies()
        for item in proxies.split('\n'):
            if item.strip() == "": continue
            ip,dc,lid,si,so = item.split(',')
            print '\tDropping linode',lid,'with IP',ip,'from dc',dc,'...'
            self.linode_cmd.linode_delete(int(lid))

        print 'done.'

    def provision(self, count=8, add=False):
        """ Provision an entirely fresh set of linodes after dropping current set """

        if not add:
            self.drop()
            
        num, idx = 0, 0

        # If we are adding Linodes without dropping, start from current count
        if add:
            start = len(self.config.get_active_proxies())
        else:
            start = 0
                        
        for i in range(start, start + count):
            # region = self.pick_region()
            # Do a round-robin on regions
            region = self.config.region_ids[idx % len(self.config.region_ids) ]
            try:
                ip, lid = self.make_new_linode(region)
                self.linode_cmd.linode_update(int(lid),
                                              'proxy' + str(i+1),
                                              self.config.group)              
                num += 1
            except Exception, e:
                print 'Error creating linode',e

            idx += 1

        print 'Provisioned',num,'linodes.'

        print >> open('proxies.list', 'w'), rotator.linode_cmd.linode_list_proxies().strip()
        print 'Saved current proxy configuration to proxies.list'
                  
    def test(self):
        """ Function to be called in loop for testing """

        proxy_out_label = ''
        region = self.pick_region()
        print 'Rotating proxy to new region',region,'...'
        # Make a test IP
        new_proxy, proxy_id = self.make_new_linode(region, test=True)
        proxy_out = self.config.get_proxy_for_rotation(least_used=True, region_switch=True,
                                                       input_region=region)     

        if proxy_out != None:
            print 'Switched out proxy',proxy_out
            proxy_out_id = int(self.config.get_proxy_id(proxy_out))
            proxy_out_label = self.linode_cmd.get_label(proxy_out_id)           

        # Switch in the new proxy
        self.config.switch_in_proxy(new_proxy, proxy_id, region)
        print 'Switched in new proxy',new_proxy
        # Write new HAProxy LB template and reload ha proxy
        self.config.write_lb_config(test=True)       
        self.send_email(proxy_out, proxy_out_label, new_proxy, region)
        
    def stop(self):
        """ Stop the rotator process """

        try:
            os.remove(self.hbf)
            # Signal the event
            self.alarm.set()
            return True
        except (IOError, OSError), e:
            pass

        return False

    def sighandler(self, signum, stack):
        """ Signal handler """

        # This will be called when you want to stop the daemon
        self.stop()
                   
    def run(self, daemon=True):
        """ Run as a background process, rotating proxies """

        # Touch heartbeat file
        open(self.hbf,'w').write('')
        # Fork
        if daemon:
            print 'Daemonizing...'
            daemonize('rotator.pid',logfile='rotator.log', drop=True)
        else:
            # Write PID anyway
            open('rotator.pid','w').write(str(os.getpid()))

        print 'Proxy rotate daemon started.'
        count = 1
        
        while True:
            # Wait on event object till woken up
            self.alarm.wait(self.config.frequency)
            status = self.alive()
            if not status:
                print 'Daemon signalled to exit. Quitting ...'
                break
                
            print 'Rotating proxy node, round #%d ...' % count
            if self.test_mode:
                self.test()
            else:
                self.rotate()
            count += 1

        sys.exit(0)
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='rotate_proxies')
    parser.add_argument('-C','--conf',help='Use the given configuration file', default='proxy.conf')    
    parser.add_argument('-s','--stop',help='Stop the currently running daemon', action='store_true')
    parser.add_argument('-t','--test',help='Run the test function to test the daemon', action='store_true')
    parser.add_argument('-n','--nodaemon',help='Run in foreground', action='store_true',default=False)
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
                        default=8)    
    
    parser.add_argument('-w','--writeconfig',help='Load current Linode proxies configuration and write a fresh proxies.list config file', action='store_true')
    parser.add_argument('-W','--writelbconfig',help='Load current Linode proxies configuration and write a fresh HAProxy config to /etc/haproxy/haproxy.cfg', action='store_true')
    parser.add_argument('--restart',help='Restart the daemon',action='store_true')

    args = parser.parse_args()
    # print args
    
    rotator = ProxyRotator(cfg=args.conf,
                           test_mode = args.test,
                           rotate=args.rotate)

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
        print >> open('proxies.list', 'w'), rotator.linode_cmd.linode_list_proxies().strip()
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
        
    rotator.run(daemon=(not args.nodaemon))
    
