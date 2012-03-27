import telnetlib
import traceback
from checks import Check

GANGLIA_HOST = "ganglia_host"
GANGLIA_PORT = "ganglia_port"

class Ganglia(Check):
    def __init__(self, logger)
        Check.__init__(self, logger)

    def check(self, agentConfig):
        try:
            self.logger.debug("Agent config: %s" % agentConfig)

            if GANGLIA_HOST not in agentConfig or agentConfig[GANGLIA_HOST] == '':
                self.logger.debug('ganglia_host configuration not set, not checking ganglia')
                return False

            host = agentConfig[GANGLIA_HOST]
            port = 8651

            if GANGLIA_PORT in agentConfig and agentConfig[GANGLIA_PORT] != '':
                port = int(agentConfig[GANGLIA_PORT])

            tn = telnetlib.Telnet(host,port)
            return tn.read_all()
        except:
            self.logger.exception("Unable to get ganglia data")
            return False
