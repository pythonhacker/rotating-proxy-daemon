import json
import time
import random
import operator
import sys
import os
from utils import enum

# Configurations

# Rotation Policies
Policy = enum('ROTATION_RANDOM',
              # Least recently used
              'ROTATION_LRU',
              # Switch to another region
              'ROTATION_NEW_REGION',
              # LRU + New region
              'ROTATION_LRU_NEW_REGION')

region_dict = {2: 'Dallas',
               3: 'Fremont',
               4: 'Atlanta',
               6: 'Newark',
               7: 'London',
               8: 'Tokyo',
               9: 'Singapore',
               10: 'Frankfurt'}


email_template = """

I just switched a proxy node in the proxy infrastructure. Details are below.

In: %(label)s, %(proxy_in)s
Out: %(label)s, %(proxy_out)s

Region: %(region)s

-- Proxy Rotator Daemon

"""

# Post process command
post_process_cmd_template = """ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s@%s "%s" """
iptables_restore_cmd = "sudo iptables-restore < /etc/iptables.rules"
squid_restart_cmd = "sudo squid3 -f /etc/squid3/squid.conf"


class ProxyConfig(object):
    """ Class representing configuration of crawler proxy infrastructure """

    def __init__(self, cfg='proxy.conf'):
        """ Initialize proxy config from the config file """

        self.parse_config(cfg)
        # This is a file with each line of the form
        # IPV4 address, datacenter code, instance-id, switch_in timestamp, switch_out timestamp
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
        except ValueError, e:
            print e
            print self.proxylist + " is empty or has junk values"
            
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

            self.proxy_dict[proxy_ip] = [proxy_ip, int(region), proxy_id, int(float(switch_in)), int(float(switch_out))]
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

    def __getattr__(self, name):
        """ Return from local, else written from config """

        try:
            return self.__dict__[name]
        except KeyError:
            return self.config.get(name)
        
    def switch_out_proxy(self, proxy):
        """ Switch out a given proxy IP """

        # Disable it
        self.proxy_state[proxy] = False
        # Mark its switched out timestamp
        self.proxy_dict[proxy][-1] = int(time.time())

    def switch_in_proxy(self, proxy, proxy_id, region):
        """ Switch in a given proxy IP """

        # Mark its switched out timestamp
        self.proxy_dict[proxy] = [proxy, int(region), proxy_id, int(time.time()), int(time.time())]
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
        # Shuffle
        items = self.proxy_dict.values()
        for i in range(10):
            random.shuffle(items)
            
        for proxy, reg, pi, si, so in items:
            if self.proxy_state[proxy]:
                lines.append('\tserver  squid%d %s:8321 check inter 10000 rise 2 fall 5' % (idx, proxy))
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

    def get_email_config(self):
        """ Return email configuration """

        return self.config['email']
    

