"""
DELL EMC ECS Email Alerting Module.
"""

from configuration.ecs_email_alert_configuration import ECSSmtpAlertConfiguration
from ecslogger import ecslogger
from ecs.ecs import ECSAuthentication
from ecs.ecs import ECSManagementAPI
from ecs.ecs import ECSUtility
from ecssqllite.ecssqllite import SQLLiteUtility
from ecssmtp.ecssmtp import ECSSMTPUtility
from ecssendgrid.ecssendgrid import ECSSendGridUtility
import sqlite3
import argparse
import datetime
import os
import traceback
import signal
import time
import logging
import threading
import json
import xml.etree.ElementTree as ET


# Constants
MODULE_NAME = "ecs-email-alert"                             # Module Name
INTERVAL = 30                                               # In seconds
CONFIG_FILE = 'ecs_email_alert_configuration.json'          # Default Configuration File
VDC_LOOKUP_FILE = 'ecs_vdc_lookup.json'                     # VDC ID Lookup File

# Globals
_configuration = None
_ecsManagementNode = None
_ecsManagementUser = None
_ecsManagementUserPassword = None
_logger = None
_ecsAuthentication = list()
_sqlLiteClient = None
_ecsVDCLookup = None
_ecsManagmentAPI = list()
_smtpClient = None
_smtpUtility = None
_sendGridUtility = None

"""
Class to listen for signal termination for controlled shutdown
"""


class ECSDataCollectionShutdown:

    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.controlled_shutdown)
        signal.signal(signal.SIGTERM, self.controlled_shutdown)

    def controlled_shutdown(self, signum, frame):
        self.kill_now = True


class ECSDataCollection (threading.Thread):
    def __init__(self, method, sqlclient, logger, ecsmanagmentapi, pollinginterval, tempDir):
        threading.Thread.__init__(self)
        self.method = method
        self.sqlclient = sqlclient
        self.logger = logger
        self.ecsmanagmentapi = ecsmanagmentapi
        self.pollinginterval = pollinginterval
        self.tempDir = tempDir

        logger.info(MODULE_NAME + '::ECSDataCollection()::init method of class called')

    def run(self):
        try:
            self.logger.info(MODULE_NAME + '::ECSDataCollection()::Starting thread with method: ' + self.method)

            if self.method == 'ecs_collect_alert_data()':
                ecs_collect_alert_data(self.logger, self.ecsmanagmentapi, self.pollinginterval, self.tempDir)
            else:
                self.logger.info(MODULE_NAME + '::ECSDataCollection()::Requested method '
                                 + self.method + ' is not supported.')
        except Exception as e:
            _logger.error(MODULE_NAME + 'ECSDataCollection::run()::The following unexpected '
                                        'exception occurred: ' + str(e) + "\n" + traceback.format_exc())


class ECSEmailAlerting (threading.Thread):
    def __init__(self, method, logger, configuration, smtpUtility, sendGridUtility):
        threading.Thread.__init__(self)
        self.method = method
        self.logger = logger
        self.configuration = configuration
        self.smtpUtility = smtpUtility
        self.sendGridUtility = sendGridUtility

        logger.info(MODULE_NAME + '::ECSSmtpAlerting()::init method of class called')

    def run(self):
        try:
            self.logger.info(MODULE_NAME + '::ECSSmtpAlerting()::Starting thread with method: ' + self.method)

            if self.method == 'ecs_send_email_alerts()':
                ecs_send_email_alerts(self.logger, self.configuration, self.smtpUtility, self.sendGridUtility)
            else:
                self.logger.info(MODULE_NAME + '::ECSSmtpAlerting()::Requested method '
                                 + self.method + ' is not supported.')
        except Exception as e:
            _logger.error(MODULE_NAME + 'ECSSmtpAlerting::run()::The following unexpected '
                                        'exception occurred: ' + str(e) + "\n" + traceback.format_exc())


def ecs_config(config, vdc_config, temp_dir):
    global _configuration
    global _logger
    global _ecsAuthentication
    global _ecsVDCLookup

    try:
        # Load and validate module configuration
        _configuration = ECSSmtpAlertConfiguration(config, temp_dir)

        # Load ECS VDC Lookup
        _ecsVDCLookup = ECSUtility(_ecsAuthentication, _logger, vdc_config)

        # Grab loggers and log status
        _logger = ecslogger.get_logger(__name__, _configuration.logging_level)
        _logger.info(MODULE_NAME + '::ecs_config()::We have configured logging level to: '
                     + logging.getLevelName(str(_configuration.logging_level)))
        _logger.info(MODULE_NAME + '::ecs_config()::Configuring ECS Data Collection Module complete.')
    except Exception as e:
        _logger.error(MODULE_NAME + '::ecs_config()::The following unexpected '
                                    'exception occured: ' + str(e) + "\n" + traceback.format_exc())


def ecs_authenticate():
    global _ecsAuthentication
    global _configuration
    global _logger
    global _ecsManagmentAPI
    connected = True

    try:
        # Wait till configuration is set
        while not _configuration:
            time.sleep(1)

        # Iterate over all ECS Connections configured and attempt tp Authenticate to ECS
        for ecsconnection in _configuration.ecsconnections:

            # Attempt to authenticate
            auth = ECSAuthentication(ecsconnection['protocol'], ecsconnection['host'], ecsconnection['user'],
                                     ecsconnection['password'], ecsconnection['port'], _logger)
            auth.connect()

            # Check to see if we have a token returned
            if auth.token is None:
                _logger.error(MODULE_NAME + '::ecs_init()::Unable to authenticate to ECS as configured.  '
                             'Please validate and try again.')
                connected = False
                break
            else:
                _ecsAuthentication.append(auth)

                # Instantiate ECS Management API object, and it to our list, and validate that we are authenticated
                _ecsManagmentAPI.append(ECSManagementAPI(auth, _logger))
                if not _ecsAuthentication:
                    _logger.info(MODULE_NAME + '::ecs_authenticate()::ECS Data Collection '
                                               'Module is not ready.  Please check logs.')
                    connected = False
                    break

        return connected

    except Exception as e:
        _logger.error(MODULE_NAME + '::ecs_authenticate()::Cannot authenticate to ECS. Cause: '
                      + str(e) + "\n" + traceback.format_exc())
        connected = False
        return connected


def sqllite_init():
    global _sqlLiteClient
    global _configuration
    global _logger
    connected = True

    try:
        # Wait till configuration is set
        while not _configuration:
            time.sleep(1)

        # Instantiate utility object and check to see if our database exists
        db_utility = SQLLiteUtility(_configuration, _logger)
        sql_database = db_utility.open_sqllite_db(_configuration.database_name)

        # If database is not found then connect with no database, create the database, and then switch to it
        if sql_database is None:
            _logger.error(MODULE_NAME + '::sqllite_init()::Unable to open/create SQLLite database as configured.  '
                                        'Please validate and try again.')
            connected = False
        else:
            _logger.info(MODULE_NAME + '::sqllite_init()::Successfully connected to SQLLite as configured.')
            _sqlLiteClient = sql_database

            # Lets check if table exits
            ecsalertstable = """ CREATE TABLE IF NOT EXISTS ecsalerts (
                                        id integer PRIMARY KEY,
                                        vdc text NOT NULL,
                                        alertId text NOT NULL,
                                        acknowledged text NOT NULL,
                                        description text NOT NULL,
                                        namespace text,
                                        severity text,
                                        symptomCode text,
                                        alertTimestamp date,
                                        emailAlerted int,
                                        alertCleared int,
                                        dateCreated date,
                                        dateEmailed date,
                                        dateCleared date
                                    ); """
            dbcur = sql_database.cursor()
            dbcur.execute(ecsalertstable)
            dbcur.close()

        return connected

    except Exception as e:
        _logger.error(MODULE_NAME + '::sqllite_init()::Cannot initialize SQL Lite database. Cause: '
                      + str(e) + "\n" + traceback.format_exc())
        connected = False
        return connected


def ecs_collect_alert_data(logger, ecsmanagmentapi, pollinginterval, tempdir):

    try:
        # Start polling loop
        while True:
            # Perform API call against each configured ECS
            for ecsconnection in ecsmanagmentapi:

                # Retrieve current alert data via API
                alert_data_file = ecsconnection.ecs_collect_alert_data(tempdir)

                if alert_data_file is None:
                    logger.info(MODULE_NAME + '::ecs_collect_alert_data()::'
                                              'Unable to retrieve ECS Dashboard Alert Information')
                    return
                else:
                    """
                    We have an XML File lets parse it
                    """
                    try:
                        tree = ET.parse(alert_data_file)
                        root = tree.getroot()

                        # Reset new alerts counter
                        new_alerts = 0

                        # Create a connection to the database
                        db_utility = SQLLiteUtility(_configuration, _logger)
                        sql_database = db_utility.open_sqllite_db(_configuration.database_name)

                        # Grab VDC Name
                        vdc = _ecsVDCLookup.vdc_json[ecsconnection.authentication.host]

                        # For each alert check if we already have it and if not add it
                        for alert in root.findall('alert'):
                            alertid = alert.find('id').text
                            acknowledged = alert.find('acknowledged').text
                            description = alert.find('description').text
                            namespace = alert.find('namespace').text
                            severity = alert.find('severity').text
                            symptomCode = alert.find('symptomCode').text
                            timestamp = alert.find('timestamp').text

                            # Check if alert already exists
                            cur = sql_database.cursor()
                            cur.execute("SELECT count(*) FROM ecsalerts WHERE alertId =?", (alertid,))
                            row = cur.fetchone()[0]

                            # If no row found for this alert id then go ahead and add the alert
                            if row == 0:
                                # If the symptom code of the alert is on the list of
                                # alerts to email add it to the database otherwise ignore it.
                                if symptomCode in _configuration.ecs_alert_symptoms_filter:
                                    current_time = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                                    alertdata = (vdc, alertid, acknowledged, description, namespace, severity,
                                                 symptomCode, timestamp, '0', '0', current_time, '', '')
                                    sql = ''' INSERT INTO ecsalerts(vdc, alertId, acknowledged, description, namespace, severity, symptomCode, alertTimestamp, emailAlerted, alertCleared, dateCreated, dateEmailed, dateCleared) VALUES(?, ?,?,?,?,?,?, ?, ?, ?, ?, ?, ?) '''
                                    cur.execute(sql, alertdata)
                                    sql_database.commit()
                                    new_alerts += 1

                        # No need to close the file as the ET parse() method will close it when parsing is completed.

                        # Close the database connection when we have processed all eligible records
                        sql_database.close()

                        _logger.info(MODULE_NAME + '::ecs_collect_alert_data::Discovered ' + str(new_alerts) +
                                     ' new alerts that were in our symptom code '
                                     'filter and added them to the extracted alerts database.')

                        _logger.debug(MODULE_NAME + '::ecs_collect_alert_data::Deleting temporary '
                                                    'json file: ' + alert_data_file )

                    except Exception as ex:
                        logger.error(MODULE_NAME + '::ecs_collect_alert_data()::The following unexpected '
                                                   'exception occurred: ' + str(ex) + "\n" + traceback.format_exc())

            if controlledShutdown.kill_now:
                logger.info(MODULE_NAME + '::ecs_collect_alert_data()::Shutdown detected.  Terminating polling.')
                break

            # Wait for specific polling interval
            time.sleep(float(pollinginterval))
    except Exception as e:
        _logger.error(MODULE_NAME + '::ecs_collect_alert_data()::The following unexpected '
                                    'exception occurred: ' + str(e) + "\n" + traceback.format_exc())


def list_alert_table(sqllite_db):
    global _logger
    """
    Query the current contents of the extracted alerts database and provide it in JSON
    """
    try:
        rowcount = 0

        _logger.info(MODULE_NAME + '::list_alert_table::About to list all extracted alerts in the database.')
        """
        Select all records in the extracted alerts table 
        """
        ecsalertsselect = """ SELECT * FROM ecsalerts; """

        cur = sqllite_db.cursor()
        cur.execute(ecsalertsselect)
        r = [dict((cur.description[i][0], value) \
                  for i, value in enumerate(row)) for row in cur.fetchall()]
        cur.connection.close()
        return r if r else None

    except Exception as e:
        _logger.error(MODULE_NAME + '::list_alert_table()::The following '
                          'unhandled exception occurred: ' + e.message)
        return None


def clear_alert_table(sqllite_db):
    """
    Clear the current contents of the extracted alerts database table
    """
    try:
        _logger.info(MODULE_NAME + '::clear_alert_table::About to clear all extracted alerts in the database.')

        # Delete all records in the extracted alerts table
        ecsalertsselect = """ DELETE FROM ecsalerts; """

        cur = sqllite_db.cursor()
        cur.execute(ecsalertsselect)
        sqllite_db.commit()
        cur.connection.close()
        return True

    except Exception as e:
        _logger.error(MODULE_NAME + '::clear_alert_table()::The following '
                          'unhandled exception occurred: ' + e.message)
        return False


def list_sent_alerts_table(sqllite_db):
    """
    Query the extracted alerts database for alerts that have been sent via SMTP and provide it in JSON
    """
    try:
        _logger.info(MODULE_NAME + '::list_sent_alerts_table::About to list all extracted alerts in the database that have had email alerts sent.')

        # Select sent records in the extracted alerts table
        ecsalertsselect = """ SELECT * FROM ecsalerts WHERE emailAlerted = 1; """

        cur = sqllite_db.cursor()
        cur.execute(ecsalertsselect)
        r = [dict((cur.description[i][0], value) \
                  for i, value in enumerate(row)) for row in cur.fetchall()]
        cur.connection.close()
        return r if r else None

    except Exception as e:
        _logger.error(MODULE_NAME + '::list_sent_alerts_table()::The following '
                          'unhandled exception occurred: ' + e.message)
        return None


def ecs_send_email_alerts(logger, configuation, smtpUtility, sendgridUtility):

    try:
        rowcount = 0

        # Retrieve polling interval based on email system being used
        if configuation.email_delivery is 'smtp':
            # SMTP email delivery is configured
            interval = configuation.smtp_alert_polling_interval
        else:
            # SendGrid email delivery is configured
            interval = configuation.send_grid_alert_polling_interval

        # Start polling loop
        while True:
            try:
                _logger.info(MODULE_NAME + '::ecs_send_email_alerts::About to poll for extracted alerts in '
                                           'the database that have not been emailed.')

                # reset sent email counter
                sent_emails = 0

                # Create a connection to the database
                db_utility = SQLLiteUtility(configuation, logger)
                sql_database = db_utility.open_sqllite_db(configuation.database_name)

                # Select records in the extracted alerts table with the
                ecsalertsselect = """ SELECT * FROM ecsalerts WHERE emailAlerted = 0; """

                sql_database.row_factory = sqlite3.Row
                cur = sql_database.cursor()
                cur.execute(ecsalertsselect)
                rows = cur.fetchall()

                # Process any returned row but sending the email and updating the sent flag.
                for row in rows:
                    if row is None:
                        break

                    # Format and send an email
                    rowcount += 1

                    # Send email based on configured email delivery system
                    if configuation.email_delivery is 'smtp':
                        # SMTP email delivery is configured
                        email_sent = configuation.smtp_alert_polling_interval
                    else:
                        # SendGrid email delivery is configured
                        email_sent = sendgridUtility.send_grid_send_email(row)

                    # Update state on row
                    current_time = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                    rowId = row[0]
                    ecsalertupdate = """ UPDATE ecsalerts SET emailAlerted = 1, dateEmailed = ? WHERE id = ?; """
                    cur.execute(ecsalertupdate, (current_time, rowId,))
                    sql_database.commit()

                    # Increment sent email count
                    sent_emails += 1

                # Close the database connection when we have processed all eligible records
                sql_database.close()

                _logger.info(MODULE_NAME + '::ecs_send_email_alerts::Processed ' + str(sent_emails) +
                             ' new alerts and sent emails.')

            except Exception as e:
                _logger.error(MODULE_NAME + '::ecs_send_email_alerts()::The following '
                                            'unhandled exception occurred: ' + e.message)

            if controlledShutdown.kill_now:
                logger.info(MODULE_NAME + '::ecs_send_email_alerts()::Shutdown detected.  Terminating polling.')
                break

            # Wait for specific polling interval
            time.sleep(float(interval))

    except Exception as e:
        _logger.error(MODULE_NAME + '::ecs_send_email_alerts()::The following unexpected '
                                    'exception occurred: ' + str(e) + "\n" + traceback.format_exc())


def ecs_data_collection():
    global _ecsAuthentication
    global _logger
    global _ecsManagmentAPI
    global _sqlLiteClient
    global _smtpClient

    try:
        # Wait till configuration is set
        while not _configuration:
            time.sleep(1)

        # Now lets spin up a thread for each API call with it's own custom polling interval by iterating
        # through our module configuration
        for i, j in _configuration.modules_intervals.items():
            method = str(i)
            interval = str(j)
            t = ECSDataCollection(method, _sqlLiteClient, _logger, _ecsManagmentAPI, interval,
                                  _configuration.tempfilepath)
            t.start()

        # Finally, spin up a thread to monitor the alerts table for alerts that have not been sent via SMTP
        t2 = ECSEmailAlerting('ecs_send_email_alerts()', _logger, _configuration, _smtpUtility, _sendGridUtility)
        t2.start()

    except Exception as e:
        _logger.error(MODULE_NAME + '::ecs_data_collection()::A failure occurred during data collection. Cause: '
                      + str(e) + "\n" + traceback.format_exc())


"""
Main 
"""
if __name__ == "__main__":

    try:
        # Command line argument processing
        helpdetail = 'ecs-email-alert provides email notification of alerts ' \
                     'generated by one or more DELL EMC Elastic Cloud Storage (ECS) clusters.'
        parser = argparse.ArgumentParser(description=helpdetail)
        parser.add_argument("-c", "--clear", help="Clear the extracted alerts database table.", action="store_true")
        parser.add_argument("-e", "--extracted", help="List all records in the extracted alerts database table.", action="store_true")
        parser.add_argument("-s", "--sent", help="List records in the extracted "
                                                 "alerts database table that have been emailed.", action="store_true")
        args = parser.parse_args()

        # Dump out application path and setup application directories
        currentApplicationDirectory = os.getcwd()
        configFilePath = os.path.abspath(os.path.join(currentApplicationDirectory, "configuration", CONFIG_FILE))
        vdcLookupFilePath = os.path.abspath(os.path.join(currentApplicationDirectory, "configuration", VDC_LOOKUP_FILE))
        tempFilePath = os.path.abspath(os.path.join(currentApplicationDirectory, "temp"))

        # Create temp diretory if it doesn't already exists
        if not os.path.isdir(tempFilePath):
            os.mkdir(tempFilePath)
        else:
            # The directory exists so lets scrub any temp XML files out that may be in there
            files = os.listdir(tempFilePath)
            for file in files:
                if file.endswith(".xml"):
                    os.remove(os.path.join(currentApplicationDirectory, "temp", file))

        # Initialize configuration object
        ecs_config(configFilePath, vdcLookupFilePath, tempFilePath)

        # Wait till we have a valid configuration object
        while not _configuration:
            time.sleep(1)

        _logger.info(MODULE_NAME + '::ecs_email_alert:main()::Configuration initialization complete.')
        _logger.info(MODULE_NAME + '::ecs_email_alert:main()::Current directory is : ' + currentApplicationDirectory)
        _logger.info(MODULE_NAME + '::ecs_email_alert:main()::Configuration file path is : ' + configFilePath)

        # Initialize the database
        if sqllite_init():

            # Process command line arguments
            if args.extracted:
                alertsJson = list_alert_table(_sqlLiteClient)
                if alertsJson:
                    print(json.dumps(alertsJson, indent=4, separators=(',', ': '), sort_keys=True))
                else:
                    _logger.error(MODULE_NAME + '::ecs_email_alert::Returned 0 extracted alerts from the .')
            else:
                if args.clear:
                    print('ECS Email Alerting')
                    # Let's make sure they really want to clear that table
                    data = input("Your about to clear all records in the alert extraction database table.  Are you sure?")

                    if data.capitalize() is 'YES':
                        clear_alert_table(_sqlLiteClient)
                else:
                    if args.sent:
                        sentAlertsJson = list_sent_alerts_table(_sqlLiteClient)
                        if sentAlertsJson:
                            print(json.dumps(sentAlertsJson, indent=4, separators=(',', ': '), sort_keys=True))
                    else:
                        continue_processing = False

                        # Now lets initialize the email delivery system
                        if _configuration.email_delivery == 'smtp':
                            _smtpUtility = ECSSMTPUtility(_configuration, _logger)
                            continue_processing = _smtpUtility.check_smtp_server_connection()
                        else:
                            _sendGridUtility = ECSSendGridUtility(_configuration, _logger)
                            continue_processing = _sendGridUtility.check_send_grid_access()

                        # If we were able to initialize our email delivery system then continue
                        if continue_processing:
                            # Perform normal alert monitoring processing

                            # Close SqlLite connection object so the data collection threads can each create their own
                            _sqlLiteClient.close()

                            # Create object to support controlled shutdown
                            controlledShutdown = ECSDataCollectionShutdown()

                            # Initialize connection to ECS(s)
                            if ecs_authenticate():

                                # Launch ECS Data Collection polling threads
                                ecs_data_collection()

                                # Check for shutdown
                                if controlledShutdown.kill_now:
                                    print(MODULE_NAME + "__main__::Controlled shutdown completed.")

    except Exception as e:
        print(MODULE_NAME + '__main__::The following unexpected error occurred: '
              + str(e) + "\n" + traceback.format_exc())

