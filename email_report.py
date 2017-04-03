import smtplib
import datetime
import sys
import socket
import os
import ses_email
import send_gmail

def email_report(config, template, content):
    """ Email any kind of report to anyone """

    print "Sending email report..."
    timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%d-%b-%Y %I:%M:%S %p")

    data = template % content
    
    if config.get('send_email', True):
        print 'Sending email ...'
        from_e, to_e = config.get('from_email'), config.get('to_email')
        from_pass = config.get('from_pass')
        subject = config.get('email_subject') % (timestamp, socket.gethostname())
        print send_gmail.send_mail(from_e, from_pass, to_e, subject, data)
        # print ses_email.send_ses(from_e, subject, data, to_e)
        print 'done.'
    else:
        print 'Not sending email.'
        # Simply print
        print data

if __name__ == "__main__":
    pass
