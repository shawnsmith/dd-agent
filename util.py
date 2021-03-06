import logging
import os
import platform
import signal
import sys
import math
import time
import uuid

try:
    from hashlib import md5
except ImportError:
    from md5 import md5

# Import json for the agent. Try simplejson first, then the stdlib version and
# if all else fails, use minjson which we bundle with the agent.
try:
    import simplejson as json
except ImportError:
    try:
        import json
    except ImportError:
        import minjson
        class json(object):
            @staticmethod
            def dumps(data):
                return minjson.write(data)

            @staticmethod
            def loads(data):
                return minjson.safeRead(data)

import yaml
try:
    from yaml import CLoader as yLoader
except ImportError:
    from yaml import Loader as yLoader

try:
    from collections import namedtuple
except ImportError:
    from compat.namedtuple import namedtuple


NumericTypes = (float, int, long)


def get_uuid():
    # Generate a unique name that will stay constant between
    # invocations, such as platform.node() + uuid.getnode()
    # Use uuid5, which does not depend on the clock and is
    # recommended over uuid3.
    # This is important to be able to identify a server even if
    # its drives have been wiped clean.
    # Note that this is not foolproof but we can reconcile servers
    # on the back-end if need be, based on mac addresses.
    return uuid.uuid5(uuid.NAMESPACE_DNS, platform.node() + str(uuid.getnode())).hex



def headers(agentConfig):
    # Build the request headers
    return {
        'User-Agent': 'Datadog Agent/%s' % agentConfig['version'],
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'text/html, */*',
    }

def getOS():
    if sys.platform == 'darwin':
        return 'mac'
    elif sys.platform.find('freebsd') != -1:
        return 'freebsd'
    elif sys.platform.find('linux') != -1:
        return 'linux'
    elif sys.platform.find('win32') != -1:
        return 'windows'
    else:
        return sys.platform

def getTopIndex():
    macV = None
    if sys.platform == 'darwin':
        macV = platform.mac_ver()
        
    # Output from top is slightly modified on OS X 10.6 (case #28239)
    if macV and macV[0].startswith('10.6.'):
        return 6
    else:
        return 5

def isnan(val):
    if hasattr(math, 'isnan'):
        return math.isnan(val)

    # for py < 2.6, use a different check
    # http://stackoverflow.com/questions/944700/how-to-check-for-nan-in-python
    return str(val) == str(1e400*0)

def cast_metric_val(val):
    # ensure that the metric value is a numeric type
    if not isinstance(val, NumericTypes):
        # Try the int conversion first because want to preserve
        # whether the value is an int or a float. If neither work,
        # raise a ValueError to be handled elsewhere
        for cast in [int, float]:
            try:
                val = cast(val)
                return val
            except ValueError:
                continue
        raise ValueError
    return val

class Watchdog(object):
    """Simple signal-based watchdog that will scuttle the current process
    if it has not been reset every N seconds.
    Can only be invoked once per process, so don't use with multiple threads.
    If you instantiate more than one, you're also asking for trouble.
    """
    def __init__(self, duration):
        """Set the duration
        """
        self._duration = int(duration)
        signal.signal(signal.SIGALRM, Watchdog.self_destruct)

    @staticmethod
    def self_destruct(signum, frame):
        try:
            import traceback
            logging.error("Self-destructing...")
            logging.error(traceback.format_exc())
        finally:
            os.kill(os.getpid(), signal.SIGKILL)

    def reset(self):
        logging.debug("Resetting watchdog for %d" % self._duration)
        signal.alarm(self._duration)


class PidFile(object):
    """ A small helper class for pidfiles. """

    PID_DIR = '/var/run/dd-agent'

    def __init__(self, program, pid_dir=PID_DIR):
        self.pid_file = "%s.pid" % program
        self.pid_dir = pid_dir
        self.pid_path = os.path.join(self.pid_dir, self.pid_file)

    def get_path(self):
        # Can we write to the directory
        try:
            if os.access(self.pid_dir, os.W_OK):
                logging.debug("Pid file is: %s" % self.pid_path)
                return self.pid_path
        except:
            logging.exception("Cannot locate pid file, defaulting to /tmp/%s" % PID_FILE)

        # if all else fails
        if os.access("/tmp", os.W_OK):
            tmp_path = os.path.join('/tmp', self.pid_file)
            logging.debug("Using temporary pid file: %s" % tmp_path)
            return tmp_path
        else:
            # Can't save pid file, bail out
            logging.error("Cannot save pid file anywhere")
            raise Exception("Cannot save pid file anywhere")

    def clean(self):
        try:
            path = self.get_path()
            logging.debug("Cleaning up pid file %s" % path)
            os.remove(path)
            return True
        except:
            logging.exception("Could not clean up pid file")
            return False

    def get_pid(self):
        "Retrieve the actual pid"
        try:
            pf = open(self.get_path())
            pid_s = pf.read()
            pf.close()

            return int(pid_s.strip())
        except:
            return None


class LaconicFilter(logging.Filter):
    """
    Filters messages, only print them once while keeping memory under control
    """
    LACONIC_MEM_LIMIT = 1024

    def __init__(self, name=""):
        logging.Filter.__init__(self, name)
        self.hashed_messages = {}

    def hash(self, msg):
        return md5(msg).hexdigest()

    def filter(self, record):
        try:
            h = self.hash(record.getMessage())
            if h in self.hashed_messages:
                return 0
            else:
                # Don't blow up our memory
                if len(self.hashed_messages) >= LaconicFilter.LACONIC_MEM_LIMIT:
                    self.hashed_messages.clear()
                self.hashed_messages[h] = True
                return 1
        except:
            return 1

class Timer(object):
    """ Helper class """

    def __init__(self):
        self.start()

    def _now(self):
        return time.time()

    def start(self):
        self.start = self._now()
        self.last = self.start
        return self

    def step(self):
        now = self._now()
        step =  now - self.last
        self.last = now
        return step

    def total(self, as_sec=True):
        return self._now() - self.start

