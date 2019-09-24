import os
import threading
import signal
import time
import collections

import email_report
from config import *

from utils import daemonize

class ProxyRotator(object):
    """ Proxy rotation, provisioning & re-configuration base class """

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
        # Actual command used for doing stuff
        self.vps_command = None
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
        new_proxy, proxy_id = self.make_new_instance(region)

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
                    proxy_out_label = self.get_instance_label(proxy_out_id)
                    print 'Removing switched out instance',proxy_out_id
                    self.delete_instance(proxy_out_id)
                else:
                    'Proxy id is 0, not removing proxy',proxy_out
        else:
            print 'Error - Did not switch out proxy as there was a problem in writing/restarting LB'

        if proxy_out_label != None:
            # Get its label and assign it to the new linode
            print 'Assigning label',proxy_out_label,'to new instance',proxy_id
            time.sleep(5)
            self.update_instance(proxy_id,
                                 proxy_out_label,
                                 self.config.group)                             

        # Post process the host
        print 'Post-processing',new_proxy,'...'
        self.post_process(new_proxy)
        self.send_email(proxy_out, proxy_out_label, new_proxy, region)

    def post_process(self, ip):
        """ Post-process a switched-in host """

        # Sleep a bit before sshing
        time.sleep(5)
        cmd = post_process_cmd_template % (self.config.user, ip, iptables_restore_cmd)
        print 'SSH command 1=>',cmd
        os.system(cmd)
        cmd = post_process_cmd_template % (self.config.user, ip, squid_restart_cmd)
        print 'SSH command 2=>',cmd     
        os.system(cmd)      

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

            # Do a round-robin on regions
            region = self.config.region_ids[idx % len(self.config.region_ids) ]
            try:
                ip, lid = self.make_new_instance(region)
                new_label = self.config.proxy_prefix + str(i+1)
                self.update_instance(int(lid),
                                     new_label,
                                     self.config.group)              
                
                num += 1
            except Exception, e:
                print 'Error creating instance',e

            idx += 1

        print 'Provisioned',num,' proxies.'
        # Save latest proxy information
        self.write_proxies()

    def write_proxies(self):
        """ Write proxies to a file """
        
        proxies_list = self.vps_command.get_proxies()
        # Randomize it
        for i in range(5):
            random.shuffle(proxies_list)

        filename = self.config.proxylist
        print >> open(filename, 'w'), '\n'.join(proxies_list)
        print 'Saved current proxy configuration to {}'.format(filename)
                  
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
                   
    def run(self):
        """ Run as a background process, rotating proxies """

        # Touch heartbeat file
        open(self.hbf,'w').write('')
        # Fork
        print 'Daemonizing...'
        daemonize('rotator.pid',logfile='rotator.log', drop=True)
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
        
    def create(self, region=3):
        """ Create a new instance for testing """

        print 'Creating new instance in region',region,'...'
        new_proxy = self.make_new_instance(region, verbose=True)

        return new_proxy

    def send_email(self, proxy_out, label, proxy_in, region):
        """ Send email upon switching of a proxy """

        print 'Sending email...'
        region = region_dict[region]
        content = email_template % locals()
        email_config = self.config.get_email_config()

        email_report.email_report(email_config, "%s", content)

    def alive(self):
        """ Return whether I should be alive """

        return os.path.isfile(self.hbf)

    def get_instance_label(self, instance_id):
        """ Return instance label given instance id """
        pass
    
    def update_instance(self, instance_id, label, group=None):
        """ Update the meta-data for the instance """
        pass

    def delete_instance(self, instance_id):
        """ Delete a given instance given its id """
        pass
    
    def drop(self):
        """ Drop all instances in current configuration (except the LB) """
        pass

