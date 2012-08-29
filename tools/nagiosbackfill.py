#!/usr/bin/python

"""Backfills nagios alerts from nagios logs files.
"""

from checks.nagios import Nagios

import logging
import socket
import sys
import optparse
import time
from dogapi import dog_http_api as dog

# Set up logging
logger = logging.getLogger("nagios")
logger.setLevel(logging.CRITICAL)
logger.addHandler(logging.StreamHandler())

# Monkey patching
def check(self, logger, agentConfig):
    # Check arguments
    self.apikey = agentConfig['api_key']
    self.events = []
    self.logger = logger
    
    # Use a generator and call self.parse_line
    self.logger.info("Nagios events for file %s" % (agentConfig['fn']))
    nagf = open(agentConfig['fn'], 'r')
    try:
        while True:
            line = nagf.next()
            self._parse_line(line)
    except StopIteration, e:
        self.logger.info("Parsed %d events" % len(self.events))
        
    return self.events

Nagios.check = check

# nagios event transform
def transform(event_data):
    is_nagios_nightly = 'CURRENT' in event_data.get('event_type', '')
    is_host_check = 'HOST' in event_data.get('event_type', '')
    is_ack = 'ack_author' in event_data
    is_passive_check = 'PASSIVE' in event_data.get('event_type', '')
    
    if is_passive_check:
        return None
    
    if is_nagios_nightly:
        return None
    
    output = event_data.copy()
    
    if is_host_check:
        check_name = event_data.get('host', 'Unknown check')
    else:
        check_name = event_data.get('check_name', 'Unknown check')
    
    event_state = event_data.get('event_state', '').lower()
    event_soft_hard = event_data.get('event_soft_hard', '').lower()
    
    output['json_payload'] = {
        'check_name': check_name,
        'event_state': event_state,
        'event_soft_hard': event_soft_hard
    }
    
    output['auto_priority'] = 0
    output['msg_text'] = event_data.get('payload', '')
    output['event_object'] = check_name
    
    # Set the alert_type
    if event_state in ['critical', 'down']:
        output['alert_type'] = "error"
    elif event_state in ['ok', 'up']:
        output['alert_type'] = "success"
    elif event_state == 'warning':
        output['alert_type'] = "warning"
    else:
        output['alert_type'] = "info"
    
    # Set the title
    if event_state == 'critical':
        output['msg_title'] = '{0} is critical'.format(
            output['event_object'])
        if 'host' in event_data:
            output['msg_title'] += ' on {0}'.format(event_data['host'])

    elif event_state == 'warning':
        output['msg_title'] = '{0} is warning'.format(output['event_object'])
        if 'host' in event_data:
            output['msg_title'] += ' on {0}'.format(event_data['host'])
        output['alert_type'] = "warning"
    
    elif event_state == 'ok':
        output['msg_title'] = '{0} is ok'.format(output['event_object'])
        if 'host' in event_data:
            output['msg_title'] += ' on {0}'.format(event_data['host'])
        output['alert_type'] = "success"
    
    elif is_host_check and event_state == 'down':
        output['msg_title'] = '{0} is down'.format(output['event_object'])

    elif is_host_check and event_state == 'up':
        output['msg_title'] = '{0} is up'.format(output['event_object'])
    
    elif is_ack:
        output['json_payload']['ack_author'] = event_data['ack_author']
    
    else:
        output['msg_title'] = output['event_object']
        if 'host' in event_data:
            output['msg_title'] += ' on {0}'.format(event_data['host'])
    
    return output

# opt parsing
parser = optparse.OptionParser()
parser.add_option("--api-key", dest="api_key")
parser.add_option("--file", help="Path to nagios log file", dest="fn")
parser.add_option("--priority", help="low to hide from main view", dest="prio", default="normal")
(options, args) = parser.parse_args()

# Run the command
nagios = Nagios(socket.getfqdn())
config = {'api_key': options.api_key, 'fn': options.fn}
events = nagios.check(logger, config)

# Submit to datadog
dog.api_key = options.api_key
ok = 0
for e in events:
    x = transform(e)
    if x is not None:
        print("(E) [{0}] {1} {2}".format(x.get("timestamp"), time.ctime(int(x.get("timestamp"))), x.get("msg_title")))
        dog.event(title=x.get("msg_title"),
                  text=x.get("msg_text"),
                  date_happened=x.get("timestamp"),
                  json_payload=x.get("json_payload"),
                  alert_type=x.get("alert_type"),
                  source_type_name="nagios",
                  priority=options.prio,
                  host=x.get("host")
                  )
        ok += 1
print("Submitted {0} Nagios events".format(ok))
