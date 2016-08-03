import smtplib
import datetime
import sys
import socket
import os

from email.mime.text import MIMEText

def email_report(config, template, content):
    """ Email any kind of report to anyone """

    print "Sending email report..."
    timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%d-%b-%Y %I:%M:%S %p")

    data = template % content
    
    if config.get('send_email', True):
        print 'Sending email ...'
        msg = MIMEText(data)
        from_e, to_e = config.get('from_email'), config.get('to_email')
        
        msg['Subject'] = config.get('email_subject') % (timestamp, socket.gethostname())
        msg['From'] = from_e
        msg['To'] = ', '.join(to_e)
        sm = smtplib.SMTP('localhost')
        sm.sendmail(from_e, to_e, msg.as_string())
        sm.quit()

        print 'done.'
    else:
        print 'Not sending email.'
        # Simply print
        print data

if __name__ == "__main__":
    pass
