# ecs-smtp-alerting configuration
----------------------------------------------------------------------------------------------
ecs-smtp-alerting is a PYTHON based script that monitors for alerts from DELL EMC's 
Elastic Cloud Storage (ECS) Product and sends emails via SMTP with alert information

ecs-smtp-alerting utilizes the ECS Managment REST API's to gather alert data from ECS which is 
then stored locally for subsequent SMTP email processing.

We've provided two sample configuration files:

- ecs_smtp_alert_configuration.sample: Change file suffix from .sample to .json and configure as needed
  This contains the tool configuration for ECS, database, and SMTP connections as well as logging level, etc. 
  
  Here is the sample configuration:
  
  BASE:
  logging_level - The default is "info" but it can be set to "debug" to generate a LOT of details
  data store - This is a placeholder for future data stores.  At the moment it's set to "influx"
  
  ECS_CONNECTION:
  protocol - Should be set to "https"
  host - This is the IP address of FQDN of an ECS node
  port - This is always "4443" which is the ECS Management API port
  user - This is the user id of an ECS Management User 
  password - This is the password for the ECS Management User
  
  _**Note: The ECS_CONNECTION is a list of dictionaries so multiple sets of ECS connection data can 
        be configured to support polling multiple ECS Clusters**_
  
  INFLUX_DATABASE_CONNECTION:
  host = This is the IP address of FQDN of the InfluxDB server
  port - This is the port that the InfluxDB server is listening on.  Default is "8086"
  user - This is the user id of the InfluxDB user 
  password - This is the password of the InfluxDB user 
  databasename - The name of the InfluxDB to connect to
  
  ECS_API_POLLING_INTERVALS
  This is a dictionary that contains the names of the ECSManagementAPI class methods that are used to perform 
  data extraction along with a numeric value that defines the polling interval in seconds to be used to call the method.
  
  "ecs_collect_local_zone_data()": "30", 
  
  "ecs_collect_local_zone_replication_data()": "60",
  
  Currently their are 7 methods in ECSManagementAPI class.  This can also be used to determine what methods should be called i.e. data     to pull.  If for some reason a user is not interested in replication data they can remove / comment out the    
  "ecs_collect_local_zone_replication_data()" line
  
  SMTP
    server = This is the IP address or FQDN of the SMTP server
    port - This is the port that the SMTP server is listening on.  Default is "25"
    user - This is the user id of the SMTP user to use to connect to the server
    password - This is the password of the SMTP user 
    fromemail - The email address that should be used as the from email when sending emails
    toemail - This is a comma seperated list of email addresses that emails should be sent to
  
- ecs_vdc_lookup.sample: Change file suffix from .sample to .json and configure as needed
  This contains a manual map of ip addresses to ECS VDC name.  This is a temporary setup workaround till we 
  dynamically grab the name during data collection.  This is simply a JSON dictionary of IP addresses to 
  VDC names.
  
  {
  "xx.xx.xx.xx": "ECSCSE-test-vdc1",
  "xx.xx.xx.xx": "ECSCSE-test-vdc1",
  "xx.xx.xx.xx": "ECSCSE-test-vdc1",
  "xx.xx.xx.xx": "ECSCSE-test-vdc1",
  "xx.xx.xx.xx": "ECSCSE-test-vdc1",
  "xx.xx.xx.xx": "ECSCSE-test-vdc2",
  "xx.xx.xx.xx": "ECSCSE-test-vdc2",
  "xx.xx.xx.xx": "ECSCSE-test-vdc2",
  "xx.xx.xx.xx": "ECSCSE-test-vdc2",
  "xx.xx.xx.xx": "ECSCSE-test-vdc2"
}

