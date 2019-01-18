"""
DELL EMC ECS SMTP Email Module.
"""
import smtplib
import time
import sys
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import xml.etree.ElementTree as ET

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

            self.logger.info(MODULE_NAME + '::check_smtp_server_connection::Successfully connected to the configured SMTP server and port at: ' + self.config.smtp_host + ':' + self.config.smtp_port)

            server.quit()

            return connected

        except Exception as e:
            self.logger.error(MODULE_NAME + '::check_smtp_server_connection()::The following '
                                            'unhandled exception occurred: ' + e.message)
            connected = False
            return connected

