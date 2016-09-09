import smtplib
import datetime
import sys
import socket
import os
import ses_email


def email_report(config, template, content):
    """ Email any kind of report to anyone """

    print "Sending email report..."
    timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%d-%b-%Y %I:%M:%S %p")

    data = template % content
    
    if config.get('send_email', True):
        print 'Sending email ...'
        from_e, to_e = config.get('from_email'), config.get('to_email')
        subject = config.get('email_subject') % (timestamp, socket.gethostname())
        print ses_email.send_ses(from_e, subject, data, to_e)
        print 'done.'
    else:
        print 'Not sending email.'
        # Simply print
        print data

if __name__ == "__main__":
    pass
