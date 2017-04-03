"""

Send email via gmail SMTP

"""

import os
import sys
import optparse
import smtplib
import time

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText


def create_message(user, recipients, subject, body):
    msg = MIMEMultipart()
    msg['From'] = user
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    msg.attach(MIMEText(body))
    return msg


def send_mail(user, password, recipients, subject, body):
    msg = create_message(user, recipients, subject, body)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(user, password)
    server.sendmail(user, recipients, msg.as_string())
    server.close()
    print('Sent email to %s' % (', '.join(recipients)))
