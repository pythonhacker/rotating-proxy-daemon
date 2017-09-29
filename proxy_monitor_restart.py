"""

Script to parse haproxy.cfg file and restart dead squid instances

"""

import re
import os
import time
import utils

server_re = re.compile(r'server\s+([a-zA-Z0-9]+)\s+(\d+\.\d+\.\d+\.\d+)\:(\d+)*')
network_test_cmd = 'nc %s %d -w 5 -zv 2>/dev/null'
squid_restart_cmd = 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@%s "sudo squid3 -f /etc/squid3/squid.conf"'

def parse_config(filename='/etc/haproxy/haproxy.cfg'):
    """ Parse HAproxy configuration file """

    restarted = {}
    
    for line in open(filename).readlines():
        line = line.strip()
        if line == '': continue

        if line.startswith('server'):
            # Get the server name out
            match = server_re.match(line)
            server_name, ip_address, port = match.groups()
            # Test for access via nc
            print ip_address, port
            cmd = network_test_cmd % (ip_address, int(port))
            if os.system(cmd) != 0:
                # This squid instance is down
                cmd = squid_restart_cmd % ip_address
                print 'Restarting squid on',ip_address,'...'
                if os.system(cmd) == 0:
                    restarted[ip_address] = 1

    print 'Restarted',len(restarted),'squid instances.'

def main():

    utils.daemonize('monitor.pid', logfile='monitor.log')
    
    while True:
        parse_config()
        time.sleep(300)
        
if __name__ == "__main__":
    import sys
    if len(sys.argv)>1:
        parse_config(sys.argv[1])
    else:
        main()
