import types

from checks import *

# Config constants
CONFIG_KEY = "mongodb_server"
SECTION_KEY = "mongo"
SERVER_KEY = "server"
PORT_KEY = "port"
DB_LOCAL = "local"
DEFAULT_PORT = 27017

class MongoDb(Check):

    def __init__(self, logger):
        Check.__init__(self, logger)
        self.counter("indexCounters.btree.accesses")
        self.counter("indexCounters.btree.hits")
        self.counter("indexCounters.btree.misses")
        self.gauge("indexCounters.btree.missRatio")
        self.counter("opcounters.insert")
        self.counter("opcounters.query")
        self.counter("opcounters.update")
        self.counter("opcounters.delete")
        self.counter("opcounters.getmore")
        self.counter("opcounters.command")
        self.counter("asserts.regular")
        self.counter("asserts.warning")
        self.counter("asserts.msg")
        self.counter("asserts.user")
        self.counter("asserts.rollovers")
        self.gauge("globalLock.ratio")
        self.gauge("connections.current")
        self.gauge("connections.available")
        self.gauge("mem.resident")
        self.gauge("mem.virtual")
        self.gauge("mem.mapped")
        self.gauge("cursors.totalOpen")
        self.gauge("cursors.timedOut")
        self.gauge("uptime")

        self.gauge("stats.indexes")
        self.gauge("stats.indexSize")
        self.gauge("stats.objects")
        self.gauge("stats.dataSize")
        self.gauge("stats.storageSize")

        self.gauge("replSet.health")
        self.gauge("replSet.state")
        self.gauge("replSet.replicationLag")

    def _build_configs(self, agentConfig):
        try:
            # Simple configuration or multiple instances
            single_conf = CONFIG_KEY in agentConfig and len(agentConfig[CONFIG_KEY]) > 0
            multiple_conf = SECTION_KEY in agentConfig

            if single_conf:
                return [(agentConfig[CONFIG_KEY], DEFAULT_PORT, None)]
            else:
                # Check for multiple instance configuration
                if multiple_conf:
                    server = lambda c, n: c[SECTION_KEY][n][SERVER_KEY]
                    port = lambda c, n: int(c[SECTION_KEY][n][PORT_KEY])
                    return [(server(agentConfig, n), port(agentConfig, n), n) for n in agentConfig[SECTION_KEY].keys()]
                else:
                    return None # No configuration
        except:
            return None

    def check(self, agentConfig, version=1):
        """
        Returns a dictionary that looks a lot like what's sent back by db.serverStatus()
        """
        try:
            # list of databases to connect to, with an optional name
            # used to use as a "device" in Datadog parlance
            # (server, port, name), name can be None.
            configs = self._build_configs(agentConfig)

            # Bail out if we don't have any config
            if configs is None: return False
            
            from pymongo import Connection

            for conf in configs:
                conn = Connection(conf[0], conf[1])
                db = conn[DB_LOCAL]

                status = db.command('serverStatus') # Shorthand for {'serverStatus': 1}
                status['stats'] = db.command('dbstats')

                # Handle replica data, if any 
                # See http://www.mongodb.org/display/DOCS/Replica+Set+Commands#ReplicaSetCommands-replSetGetStatus
                try: 
                    data = {}

                    replSet = conn['admin'].command('replSetGetStatus')
                    if replSet:
                        primary = None
                        current = None

                        # find nodes: master and current node (ourself)
                        for member in replSet['members']:
                            if member['self']:
                                current = member
                            if member['state'] == 1:
                                primary = member

                        # If we have both we can compute a lag time
                        if current is not None and primary is not None:
                            lag = current['optimeDate'] - primary['optimeDate']
                            # Python 2.7 has this built in, python < 2.7 doesn't...
                            if hasattr(lag,'total_seconds'):
                                data['replicationLag'] = lag.total_seconds()
                            else:
                                data['replicationLag'] = (lag.microseconds + \
                    (lag.seconds + lag.days * 24 * 3600) * 10**6) / 10.0**6

                        if current is not None:
                            data['health'] = current['health']

                        data['state'] = replSet['myState']
                        status['replSet'] = data
                except:
                    pass

                # If these keys exist, remove them for now as they cannot be serialized
                try:
                    status['backgroundFlushing'].pop('last_finished')
                except KeyError:
                    pass
                try:
                    status.pop('localTime')
                except KeyError:
                    pass

                # Flatten the metrics first
                # Collect samples
                # Send a dictionary back
                r = {}

                for m in self.get_metrics():
                    # each metric is of the form: x.y.z with z optional
                    # and can be found at status[x][y][z]
                    value = status
                    try:
                        for c in m.split("."):
                            value = value[c]
                    except KeyError:            
                        continue

                    # value is now status[x][y][z]
                    assert type(value) in (types.IntType, types.LongType, types.FloatType)

                    self.save_sample(m, value)

                    # opposite op: x.y.z -> r[x][y][zPS], yes, ...PS for counters
                    try:
                        val = self.get_sample(m)
                        for c in m.split(".")[:-1]:
                            if c not in r:
                                r[c] = {}
                            r = r[c]
                        if self.is_counter(m):
                            suffix = m.split(".")[-1] + "PS"
                        else:
                            suffix = m.split(".")[-1]
                        r[suffix] = val

                    except UnknownValue:
                        pass

                if version == 1:
                    return r
                elif version == 2:
                    raise Exception("Not supported")

        except ImportError:
            self.logger.exception('Unable to import pymongo library.')
            return False

        except:
            self.logger.exception('Unable to get MongoDB status')
            return False

if __name__ == "__main__":
    import logging
    agentConfig = { 'mongodb_server': 'localhost:27017' }
    db = MongoDb(logging)
    print db.check(agentConfig)
