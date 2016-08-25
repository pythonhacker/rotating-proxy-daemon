from fabric.api import run
from fabric.api import hosts, local, settings, abort
from fabric.state import env

import os

def process_proxy_host():
    """ Post-process a proxy host """

    with settings(warn_only=True):
        run("sudo iptables-restore < /etc/iptables.rules")
        run("pgrep -f squid3; if [ $? -eq 1 ]; then sudo squid3 -f /etc/squid3/squid.conf; fi")
        
def iptables_apply():
    """ Apply iptables rules from /etc/iptables.rules """

    with settings(warn_only=True):
        run("sudo iptables-restore < /etc/iptables.rules")

def proxy_iptables():
    """ Apply iptables rules on all proxy nodes """

    # get proxy list from proxylb
    local('scp alpha@proxylb:proxyrotate/proxies.list .')
    if os.path.isfile('proxies.list'):
        for line in open('proxies.list'):
            ip = line.strip().split(',')[0].strip()
            env.host_string = ip
            env.user = 'alpha'
            print 'Restoring iptables rules on',ip,'...'
            run('sudo iptables-restore < /etc/iptables.rules')


def install_keys():
    """ Install an ssh key to all proxy nodes """

    # get proxy list from proxylb
    local('scp alpha@proxylb:proxyrotate/proxies.list .')
    if os.path.isfile('proxies.list'):
        for line in open('proxies.list'):
            ip = line.strip().split(',')[0].strip()
            env.host_string = ip
            env.user = 'alpha'
            local('scp id_rsa.pub alpha@%s:' % ip)
            run('cat id_rsa.pub >> .ssh/authorized_keys')


