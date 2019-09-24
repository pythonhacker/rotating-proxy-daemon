""" Utility functions & classes """

import os
import sys
import pwd
import uuid
import functools

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

if __name__ == "__main__":
    pass

        
