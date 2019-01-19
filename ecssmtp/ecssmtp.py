"""
DELL EMC ECS SMTP Email Module.
"""


import smtplib
import time
import email.message

# Constants
MODULE_NAME = "ecssmtp"                  # Module Name

class ECSSMTPException(Exception):
    pass


class ECSSMTPUtility(object):
    """
    Stores ECS SMTP Email Functions
    """
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def check_smtp_server_connection(self):
        """
        Checks if a database exists and create if it doesn't
        """
        try:
            connected = True

            while not self.config:
                time.sleep(1)

            # Create SMTP server and handshake
            server = smtplib.SMTP(self.config.smtp_host + ':' + self.config.smtp_port)
            server.connect(self.config.smtp_host + ':' + self.config.smtp_port)

            self.logger.info(MODULE_NAME + '::check_smtp_server_connection::Successfully '
                                           'connected to the configured SMTP server and port at: ' + self.config.smtp_host + ':' + self.config.smtp_port)

            server.quit()

            return connected

        except Exception as e:
            self.logger.error(MODULE_NAME + '::check_smtp_server_connection()::The following '
                                            'unhandled exception occurred: ' + e.message)
            connected = False
            return connected

    def smtp_send_email(self, row):

        try:
            sent = True

            while not self.config:
                time.sleep(1)

            # Grab values from row parameter
            id = row[0]
            vdc = row[1]
            alertid = row[2]
            description = row[4]
            severity = row[6]
            symtomcode = row[7]
            timestamp = row[8]

            # Setup message object
            msg = email.message.Message()

            msg['Subject'] = "Elastic Cloud Storage (ECS) Alert Received"
            msg['From'] = self.config.smtp_fromemail
            msg['To'] = self.config.smtp_toemail

            if severity == 'WARNING':
                severity_text = """<font color="orange">""" + severity + "</font>"
            else:
                if severity == 'ERROR':
                    severity_text = """<font color="red">""" + severity + "</font>"
                else:
                    severity_text = """<font color="black">""" + severity + "</font>"

            # Set email HTML content
            email_content = """
            <html>
            <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
               <title>Elastic Cloud Storage (ECS) Alert Received</title>
            </head> 
            <html><body><h1>Elastic Cloud Storage (ECS) Received Alert from Virtual Data Center: {0} </h1><br>
            Severity: {1} <br>
            Symptom Code : {2} <br>
            Description : {3}<br>
            Timestamp : {4} <br>
            </body></html>"""

            # Format message
            msg.add_header('Content-Type', 'text/html')
            msg.set_payload(email_content.format(vdc, severity_text, symtomcode, description, timestamp))

            # Connect to server and send email
            s = smtplib.SMTP(self.config.smtp_host + ':' + self.config.smtp_port)

            # If authentication is required attempt to login to server with configured user and password
            if self.config.smtp_authentication_required == '1':
                s.login(self.config.smtp_user, self.config.smtp_password)

            # Send email
            s.sendmail(msg['From'], [msg['To']], msg.as_string())

            return sent

        except Exception as e:
            self.logger.error(MODULE_NAME + '::smtp_send_email()::The following '
                                            'unhandled exception occurred: ' + e.message)
            sent = False
            return sent
