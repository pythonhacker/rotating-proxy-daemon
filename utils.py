""" Utility functions & classes """

import os
import sys
import pwd
import uuid
import functools
import boto3

def enum(*sequential, **named):
    enums = dict(zip(sequential, range(len(sequential))), **named)
    return type('Enum', (), enums)

def randpass():
    """ Return a random password """
    return uuid.uuid4().bytes.encode('base64')[:16]

class Log(object):
    """A dead-simple, stupid logging class """

    def __init__(self, f):
        self.f = f

    def write(self, s):
        try:
            s = unicode(s, 'ascii', 'ignore').encode()
        except TypeError:
            s = s.encode('ascii', 'ignore')
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.f.flush()


def drop_privileges(uid_name='alpha', gid_name='alpha'):
    """ Drop privileges of current process to given user and group """
    
    if os.getuid() != 0:
        # We're not root so, like, whatever dude
        return

    # Get the uid/gid from the name
    pwstruct = pwd.getpwnam(uid_name)
    running_uid = pwstruct.pw_uid
    running_gid = pwstruct.pw_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(running_gid)
    os.setuid(running_uid)

    # Ensure a very conservative umask
    old_umask = os.umask(077)
    
def daemonize(pidfile, logfile=None, user='ubuntu', drop=True):
    """ Make a daemon with the given pidfile and optional logfile """
    
    # Disconnect from controlling TTY as a service
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError, e:
        print >>sys.stderr, "fork #1 failed: %d (%s)" % (e.errno, e.strerror)
        sys.exit(1)

    # Do not prevent unmounting...
    os.setsid()
    os.umask(0)

    # do second fork
    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent, print eventual PID before
            #print "Daemon PID %d" % pid
            open(pidfile,'w').write("%d"%pid)
            sys.exit(0)
    except OSError, e:
        print >>sys.stderr, "fork #2 failed: %d (%s)" % (e.errno, e.strerror)
        sys.exit(1)

    # Drop privileges to given user by default
    if drop:
        drop_privileges(user, user)
    
    # Redirect stdout/stderr to log file
    if logfile != None:
        log=Log(open(logfile,'a'))
        sys.stdout.close()
        sys.stderr.close()
        sys.stdin.close()
        sys.stdout=sys.stderr=log

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
            method_name = 'linode_' + cmd
            method = functools.partial(self._run, cmd)
            if self.verbose: print 'Dyn-creating method',method_name,'...'
            setattr(self, method_name, method)
            
    def get_label(self, linode_id):
        """ Return the label, given the linode id """

        data = self.linode_info(linode_id)
        return data.split('\n')[0].split(':')[-1].strip()

class AWSCommand(object):
    '''Class encapsulating the aws ec2 API'''
    def __init__(self, config=None):
        self.ec2 = boto3.resource('ec2')
        self.config = config

    def create_ec2(self, **params):
        return self.ec2.create_instances(MaxCount=1, MinCount=1, **params)[0]

    def list_proxies(self):
        proxies = []
        filters=[
            {'Name':'image-id', 'Values':[self.config.aws_image_id]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
        for instance in self.ec2.instances.filter(Filters=filters):
            proxies.append(','.join([instance.public_ip_address, '', instance.id,'0','0']))
        return proxies

    def delete_ec2(self, instance_id):
        instance = self.ec2.Instance(instance_id)
        instance.terminate()
        instance.wait_until_terminated()

if __name__ == "__main__":
    l = LinodeCommand()
    l.get_label(int(sys.argv[1]))

        
