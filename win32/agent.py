import win32serviceutil
import win32service
import win32event
import servicemanager
import sys
import logging
import tornado.httpclient
import threading
import modules
import time
import _winreg
import os
from optparse import Values

from checks.collector import Collector
from emitter import http_emitter
from win32.common import handle_exe_click
import dogstatsd
from ddagent import Application
from config import (get_config, set_win32_cert_path, get_system_stats,
    load_check_directory)
from win32.common import handle_exe_click

RESTART_INTERVAL = 4 * 24 * 60 * 60 # 4 days

# Globals
agent_logger = logging.getLogger('agent')

class AgentSvc(win32serviceutil.ServiceFramework):
    _svc_name_ = "ddagent"
    _svc_display_name_ = "Datadog Agent"
    _svc_description_ = "Sends metrics to Datadog"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        config = get_config(parse_args=False)
        self.forwarder = DDForwarder(config)
        self.dogstatsd = DogstatsdThread(config)

        # Setup the correct options so the agent will use the forwarder
        opts, args = Values({
            'dd_url': None,
            'clean': False,
            'use_forwarder': True,
            'disabled_dd': False
        }), []
        agentConfig = get_config(init_logging=True, parse_args=False,
            options=opts)

        # Create the registry key, if needed
        AgentRegistry.init()

        self.agent = DDAgent(agentConfig)
        self.restart_interval = int(agentConfig.get('restart_interval', RESTART_INTERVAL))

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

        # Stop all services
        self.forwarder.stop()
        self.agent.stop()
        self.dogstatsd.stop()
        self.running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                servicemanager.PYS_SERVICE_STARTED,
                                (self._svc_name_, ''))
        # Start all services
        self.forwarder.start()
        self.agent.start()
        self.dogstatsd.start()

        # Loop to keep the service running since all DD services are
        # running in separate threads
        self.running = True
        while self.running:
            if self._should_restart():
                self._do_restart()
            else:
                time.sleep(1)

    def _should_restart(self):
        now = time.time()
        if now - self.agent_start >= self.restart_interval:
            return True
        return False

    def _do_restart(self):
        agent_logger.log("Going to restart the agent because %s seconds have passed" \
             % (self.restart_interval))

        # Flip the 'autorestart' flag so the agent start event isn't sent
        AgentRegistry.set_value('autorestart', 1)

        # Make a call to "net" to stop and start this service
        os.system("net stop DatadogAgent && net start DatadogAgent")

class DDAgent(threading.Thread):
    def __init__(self, agentConfig):
        threading.Thread.__init__(self)
        self.config = agentConfig
        # FIXME: `running` flag should be handled by the service
        self.running = True

    def run(self):
        emitters = self.get_emitters()
        systemStats = get_system_stats()
        collector = Collector(self.config, emitters, systemStats)
        disable_start_event = self._should_disable_start_event()

        # Load the checks.d checks
        checksd = load_check_directory(self.config)

        # Main agent loop will run until interrupted
        while self.running:
            collector.run(checksd=checksd)
            time.sleep(self.config['check_freq'])

    def stop(self):
        self.running = False

    def get_emitters(self):
        emitters = [http_emitter]
        custom = [s.strip() for s in
            self.config.get('custom_emitters', '').split(',')]
        for emitter_spec in custom:
            if not emitter_spec:
                continue
            emitters.append(modules.load(emitter_spec, 'emitter'))

        return emitters

    def _should_disable_start_event(self):
        ''' Read the 'autorestart' flag from the Agent registry. If it is marked
            as true (>0) then we should not send an Agent start event. We also
            want to flip the flag back off.
        '''
        autorestart = AgentRegistry.get_value('autorestart')
        if autorestart > 0:
            # turn the flag off
            AgentRegistry.set_value('autorestart', 0)
            return True

        return False


class DDForwarder(threading.Thread):
    def __init__(self, agentConfig):
        threading.Thread.__init__(self)
        set_win32_cert_path()
        self.config = get_config(parse_args = False)
        port = agentConfig.get('listen_port', 17123)
        if port is None:
            port = 17123
        else:
            port = int(port)
        self.port = port
        self.forwarder = Application(port, agentConfig, watchdog=False)

    def run(self):
        self.forwarder.run()

    def stop(self):
        self.forwarder.stop()


class DogstatsdThread(threading.Thread):
    def __init__(self, agentConfig):
        threading.Thread.__init__(self)
        self.reporter, self.server = dogstatsd.init(use_forwarder=True)

    def run(self):
        self.reporter.start()
        self.server.start()

    def stop(self):
        self.server.stop()
        self.reporter.stop()


class AgentRegistry(object):
    REGISTRY_KEY = r'Software\Datadog\Datadog Agent\Main'

    @classmethod
    def init(cls):
        try:
            _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, cls.REGISTRY_KEY,
                0, _winreg.KEY_ALL_ACCESS)
        except WindowsError:
            # Create the registry key if we haven't already
            _winreg.CreateKey(_winreg.HKEY_CURRENT_USER, cls.REGISTRY_KEY)

    @classmethod
    def get_value(cls, value):
        try:
            key = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, cls.REGISTRY_KEY,
                0, _winreg.KEY_ALL_ACCESS)
        except WindowsError:
            # make this a better error message
            raise Exception('Unable to open HKEY_CURRENT_USER\%s' % (cls.REGISTRY_KEY))

        val, reg_type = _winreg.QueryValueEx(key, value)
        return val

    @classmethod
    def set_value(cls, reg_key, value, value_type=_winreg.REG_DWORD):
        try:
            key = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, cls.REGISTRY_KEY,
                0, _winreg.KEY_ALL_ACCESS)
        except WindowsError:
            # make this a better error message
            raise Exception('Unable to open HKEY_CURRENT_USER\%s' % (cls.REGISTRY_KEY))

        _winreg.SetValueEx(key, reg_key, 0, value_type, value)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        handle_exe_click(AgentSvc._svc_name_)
    else:
        win32serviceutil.HandleCommandLine(AgentSvc)
