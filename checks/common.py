# Core modules
import os
import re
import logging
import platform
import subprocess
import sys
import time
import datetime
import socket

# Needed to identify server uniquely
import uuid
try:
    from hashlib import md5
except ImportError: # Python < 2.5
    from md5 import new as md5

from config import get_version

from checks import gethostname

from checks.nagios import Nagios
from checks.build import Hudson

from checks.db.mysql import MySql
from checks.db.mongo import MongoDb
from checks.db.redisDb import Redis
from checks.db.couch import CouchDb
from checks.db.pg import PostgreSql
from checks.db.mcache import Memcache

from checks.queue import RabbitMq
from checks.system import Disk, IO, Load, Memory, Network, Processes, Cpu
from checks.web import Apache, Nginx
from checks.ganglia import Ganglia
from checks.cassandra import Cassandra
from checks.datadog import Dogstreams, DdForwarder

from checks.jmx import Jvm, Tomcat, ActiveMQ, Solr

from resources.processes import Processes as ResProcesses

def getUuid():
    # Generate a unique name that will stay constant between
    # invocations, such as platform.node() + uuid.getnode()
    # Use uuid5, which does not depend on the clock and is
    # recommended over uuid3.
    # This is important to be able to identify a server even if
    # its drives have been wiped clean.
    # Note that this is not foolproof but we can reconcile servers
    # on the back-end if need be, based on mac addresses.
    return uuid.uuid5(uuid.NAMESPACE_DNS, platform.node() + str(uuid.getnode())).hex

class checks:
    def __init__(self, agentConfig, rawConfig, emitter):
        self.agentConfig = agentConfig
        self.rawConfig = rawConfig
        self.plugins = None
        self.emitter = emitter
        self.last_post_ts = None
        
        macV = None
        if sys.platform == 'darwin':
            macV = platform.mac_ver()
            macV_minor_version = int(re.match(r'10\.(\d+)\.?.*', macV[0]).group(1))
        
        # Output from top is slightly modified on OS X 10.6 (case #28239) and greater
        if macV and (macV_minor_version >= 6):
            self.topIndex = 6
        else:
            self.topIndex = 5
    
        self.os = None
        
        self.checksLogger = logging.getLogger('checks')
        # Set global timeout to 15 seconds for all sockets (case 31033). Should be long enough
        socket.setdefaulttimeout(15)
        
        self.linuxProcFsLocation = self.getMountedLinuxProcFsLocation()
        
        self._apache = Apache(self.checksLogger)
        self._nginx = Nginx(self.checksLogger)
        self._disk = Disk(self.checksLogger)
        self._io = IO(self.checksLogger)
        self._load = Load(self.checksLogger, self.linuxProcFsLocation)
        self._memory = Memory(self.checksLogger, self.linuxProcFsLocation, self.topIndex)
        self._network = Network(self.checksLogger)
        self._processes = Processes(self.checksLogger)
        self._cpu = Cpu(self.checksLogger)
        self._couchdb = CouchDb(self.checksLogger)
        self._mongodb = MongoDb(self.checksLogger)
        self._mysql = MySql(self.checksLogger)
        self._pgsql = PostgreSql(self.checksLogger)
        self._rabbitmq = RabbitMq(self.checksLogger)
        self._ganglia = Ganglia(self.checksLogger)
        self._cassandra = Cassandra(self.checksLogger)
        self._redis = Redis(self.checksLogger)
        self._jvm = Jvm(self.checksLogger)
        self._tomcat = Tomcat(self.checksLogger)
        self._activemq = ActiveMQ(self.checksLogger)
        self._solr = Solr(self.checksLogger)
        self._memcache = Memcache(self.checksLogger)
        self._dogstream = Dogstreams.init(self.agentConfig)
        self._ddforwarder = DdForwarder(self.agentConfig)

        self._event_checks = [Hudson(), Nagios(socket.gethostname())]
        self._resources_checks = [ResProcesses(self.checksLogger,self.agentConfig)]
    

    def updateLastPostTs(self):
        """Simple accessor to make it obvious that it is meant to work with late()
        """
        self.last_post_ts = time.time()

    def lastPostTs(self): return self.last_post_ts

    def doChecks(self, firstRun=False, systemStats=False):
        """Actual work"""
        self.checksLogger.info("Starting checks")

        cpuStats  = self._cpu.check(self.agentConfig)
        ioStats   = self._io.check(self.agentConfig)
        diskUsage = self._disk.check(self.agentConfig)
        loadAvrgs = self._load.check(self.agentConfig)
        memory    = self._memory.check(self.agentConfig)
        processes = self._processes.check(self.agentConfig)

        apacheStatus   = self._apache.check(self.agentConfig)
        mysqlStatus    = self._mysql.check(self.agentConfig)
        pgsqlStatus    = self._pgsql.check(self.agentConfig)
        networkTraffic = self._network.check(self.agentConfig)
        nginxStatus    = self._nginx.check(self.agentConfig)
        rabbitmq       = self._rabbitmq.check(self.agentConfig)
        mongodb        = self._mongodb.check(self.agentConfig)
        couchdb        = self._couchdb.check(self.agentConfig)

        gangliaData    = self._ganglia.check(self.agentConfig)
        cassandraData  = self._cassandra.check(self.agentConfig)
        redisData      = self._redis.check(self.agentConfig)
        jvmData        = self._jvm.check(self.agentConfig)
        tomcatData     = self._tomcat.check(self.agentConfig)
        activeMQData   = self._activemq.check(self.agentConfig)
        solrData       = self._solr.check(self.agentConfig)
        memcacheData   = self._memcache.check(self.agentConfig)
        dogstreamData  = self._dogstream.check(self.agentConfig)
        ddforwarderData = self._ddforwarder.check(self.agentConfig)
        self.checksLogger.info("Checks done")

        checksData = {
            'collection_timestamp': time.time(),
            'os' : self.os,
            'python': sys.version,
            'agentVersion' : self.agentConfig['version'], 
            'loadAvrg1' : loadAvrgs['1'], 
            'loadAvrg5' : loadAvrgs['5'], 
            'loadAvrg15' : loadAvrgs['15'], 
            'memPhysUsed' : memory['physUsed'], 
            'memPhysFree' : memory['physFree'], 
            'memSwapUsed' : memory['swapUsed'], 
            'memSwapFree' : memory['swapFree'], 
            'memCached' : memory['cached'], 
            'networkTraffic' : networkTraffic, 
            'processes' : processes,
            'apiKey': self.agentConfig['apiKey'],
            'events': {},
            'resources': {},
        }

        if diskUsage is not False and len(diskUsage) == 2:
            checksData["diskUsage"] = diskUsage[0]
            checksData["inodes"] = diskUsage[1]
            
        if cpuStats is not False and cpuStats is not None:
            checksData.update(cpuStats)

        if gangliaData is not False and gangliaData is not None:
            checksData['ganglia'] = gangliaData
           
        if cassandraData is not False and cassandraData is not None:
            checksData['cassandra'] = cassandraData
 
        if apacheStatus:    checksData.update(apacheStatus)
        if mysqlStatus:     checksData.update(mysqlStatus)
        if pgsqlStatus:     checksData['postgresql'] = pgsqlStatus
        if nginxStatus:     checksData.update(nginxStatus)
        if rabbitmq:        checksData['rabbitMQ'] = rabbitmq
        if mongodb:         checksData['mongoDB'] = mongodb
        if couchdb:         checksData['couchDB'] = couchdb
        if ioStats:         checksData['ioStats'] = ioStats
        if redisData:       checksData['redis'] = redisData
        if jvmData:         checksData['jvm'] = jvmData
        if tomcatData:      checksData['tomcat'] = tomcatData
        if activeMQData:    checksData['activemq'] = activeMQData
        if solrData:        checksData['solr'] = solrData
        if memcacheData:    checksData['memcache'] = memcacheData
        if dogstreamData:   checksData.update(dogstreamData)
        if ddforwarderData: checksData['datadog'] = ddforwarderData
 
        # Include server indentifiers
        checksData['internalHostname'] = gethostname(self.agentConfig)
        checksData['uuid'] = getUuid()
        
        # Process the event checks. 
        for event_check in self._event_checks:
            event_data = event_check.check(self.checksLogger, self.agentConfig)
            if event_data:
                checksData['events'][event_check.key] = event_data
       
       # Include system stats on first postback
        if firstRun:
            checksData['systemStats'] = systemStats
            if self.agentConfig['tags'] is not None:
                checksData['tags'] = self.agentConfig['tags']
            # Also post an event in the newsfeed
            checksData['events']['System'] = [{'api_key': self.agentConfig['apiKey'],
                                               'host': checksData['internalHostname'],
                                               'timestamp': int(time.mktime(datetime.datetime.now().timetuple())),
                                               'event_type':'Agent Startup',
                                               'msg_text': 'Version %s' % get_version()
                                            }]
       
        # Resources checks
        has_resource = False
        for resources_check in self._resources_checks:
            resources_check.check()
            snaps = resources_check.pop_snapshots()
            if snaps:
                has_resource = True
                res_value = { 'snaps': snaps,
                              'format_version': resources_check.get_format_version() }                              
                res_format = resources_check.describe_format_if_needed()
                if res_format is not None:
                    res_value['format_description'] = res_format
                checksData['resources'][resources_check.RESOURCE_KEY] = res_value
 
        if has_resource:
            checksData['resources']['meta'] = {
                        'api_key': self.agentConfig['apiKey'],
                        'host': checksData['internalHostname'],
                    }


        # Send back data
        self.checksLogger.debug("checksData: %s" % checksData)
        self.emitter(checksData, self.checksLogger, self.agentConfig)
        self.updateLastPostTs()
        
    def getMountedLinuxProcFsLocation(self):
        # Lets check if the Linux like style procfs is mounted
        mountedPartitions = subprocess.Popen(['mount'], stdout = subprocess.PIPE, close_fds = True).communicate()[0]
        location = re.search(r'linprocfs on (.*?) \(.*?\)', mountedPartitions)
        
        # Linux like procfs file system is not mounted so we return False, else we return mount point location
        if location == None:
            return False

        location = location.group(1)
        return location
