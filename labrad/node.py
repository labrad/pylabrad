# Copyright (C) 2007  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
labrad.node

Provides an interface to manage all python labrad servers
running on a particular computer.  This version runs each
server in a separate process, so that they can not interfere
with each other.  Information such as the manager host, port
and password are passed to the child process in environment
variables or via command line arguments.  The startup process
for each child server is controlled by an associated .ini file.
"""

import os
import re
import sys
from datetime import datetime
from ConfigParser import SafeConfigParser

from labrad import util
from labrad.config import ConfigFile
from labrad.server import ILabradServer, LabradServer, setting
from labrad.util import dispatcher, findEnvironmentVars, interpEnvironmentVars

from twisted.application.service import IService, MultiService
from twisted.application.internet import TCPClient
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessDone, ProcessTerminated
from twisted.python import log
from twisted.python.components import registerAdapter
from twisted.plugin import getPlugins

from zope.interface import Interface, implements

LOG_LENGTH = 1000 # maximum number of lines of stdout to keep per server

class IServerProcess(Interface):
    pass
    
class ServerProcess(ProcessProtocol):
    """A class to represent a running server instance."""
    implements(IServerProcess)
    timeout = 20

    def __init__(self, env):
        self.env = os.environ.copy()
        self.env.update(env)
        cls = self.__class__
        self.name = interpEnvironmentVars(cls.instancename, self.env)
        self.cmdline = interpEnvironmentVars(cls.cmdline, self.env)
        self.args = self.cmdline.split()
        self.executable = os.path.join(self.path, self.args[0])

        self.starting = False
        self.running = False
        self.startup = util.DeferredSignal()
        self.shutdown = util.DeferredSignal()
        self.output = []

    @inlineCallbacks
    def start(self):
        if self.running:
            return
        
        print "starting '%s'..." % self.name
        print "path:", self.path
        print "executable:", self.executable
        print "args:", self.args

        startd = self.startup()
        self.starting = True
        dispatcher.connect(self.serverConnected, "serverConnected")
        dispatcher.send("server_starting", sender=self, server=self.name)
        self.proc = reactor.spawnProcess(self, self.executable, self.args,
                                         env=self.env, path=self.path)
        timeoutCall = reactor.callLater(self.timeout, self.kill)
        try:
            yield startd
            dispatcher.send("server_started", sender=self, server=self.name)
        finally:
            self.starting = False
            if timeoutCall.active():
                timeoutCall.cancel()
            dispatcher.disconnect(self.serverConnected, "serverConnected")
        
    def serverConnected(self, ID, name):
        """Called when a server connects to LabRAD.
        
        We check if the server name matches the name we are looking for.
        """
        if name == self.name:
            self.ID = ID
            self.running = True
            self.startup.callback(self)

    def processEnded(self, reason):
        if isinstance(reason.value, ProcessDone):
            print "'%s': process closed cleanly." % self.name
        elif isinstance(reason.value, ProcessTerminated):
            print "'%s': process terminated: %s" % (self.name, reason.value)
        else:
            print "'%s': process ended: %s" % (self.name, reason)
        self.running = False
        if self.starting:
            self.startup.errback(Exception('Startup failed.'))
        else:
            self.shutdown.callback(self)

    @inlineCallbacks
    def stop(self):
        if not self.running:
            return
        print "stopping '%s'..." % self.name
        dispatcher.send("server_stopping", sender=self, server=self.name)
        d = self.shutdown()
        self.kill()
        yield d
        dispatcher.send("server_stopped", sender=self, server=self.name)

    def kill(self):
        # TODO: implement custom shutdown methods
        try:
            #self.proc.writeToChild(0, '\x03')
            self.proc.signalProcess("KILL")
            #self.client._cxn.sendMessage(self.ID, [(987654321, None)])
        except:
            pass

    @inlineCallbacks
    def restart(self):
        yield self.stop()
        yield self.start()

    def outReceived(self, data):
        self.output.append((datetime.now(), data))
        self.output = self.output[-LOG_LENGTH:]
        print "'%s' stdout: %s" % (self.name, data)

    def errReceived(self, data):
        self.output.append((datetime.now(), data))
        self.output = self.output[-LOG_LENGTH:]
        print "'%s' stderr: %s" % (self.name, data)

    def clearOutput(self):
        self.output = []

    def inConnectionLost(self):
        print "'%s': lost stdin." % self.name
        self.kill()

    def outConnectionLost(self):
        print "'%s': lost stdout." % self.name
        self.kill()

    def errConnectionLost(self):
        print "'%s': lost stderr." % self.name
        self.kill()

def createGenericServerCls(path, filename):
    scp = SafeConfigParser()
    scp.read(os.path.join(path, filename))

    class cls(ServerProcess):
        pass

    # general information
    cls.name = scp.get('info', 'name', raw=True)
    cls.__doc__ = scp.get('info', 'description', raw=True)
    if scp.has_option('info', 'version'):
        cls.version = scp.get('info', 'version', raw=True)
    else:
        cls.version = '0.0'
    try:
        cls.instancename = scp.get('info', 'instancename', raw=True)
    except:
        cls.instancename = cls.name
    cls.environVars = findEnvironmentVars(cls.instancename)
    cls.isLocal = len(cls.environVars) > 0

    # startup
    cls.cmdline = scp.get('startup', 'cmdline', raw=True)
    cls.path = path
    try:
        cls.timeout = float(scp.getint('startup', 'timeout'))
    except:
        pass

    return cls

def createPythonServerCls(plugin):
    class cls(ServerProcess):
        pass

    cls.name = plugin.name
    cls.__doc__ = plugin.__doc__
    if hasattr(plugin, 'version'):
        cls.version = plugin.version
    else:
        cls.version = '0.0'
    if hasattr(plugin, 'instanceName'):
        cls.instancename = plugin.instanceName
    else:
        cls.instancename = plugin.name
    cls.environVars = findEnvironmentVars(cls.instancename)
    cls.isLocal = len(cls.environVars) > 0
    
    # startup
    cls.cmdline = ' '.join([sys.executable, '-m', plugin.__module__])
    cls.path = os.path.split(sys.modules[plugin.__module__].__file__)[0]
    return cls

class IProcNode(Interface):
    pass

class ProcNode(MultiService):
    implements(IProcNode)

    reconnectDelay = 10

    def __init__(self, name, host, port):
        MultiService.__init__(self)
        self.name = name
        self.host = host
        self.port = port

    def startService(self):
        MultiService.startService(self)
        self.startConnection()

    def startConnection(self):
        print 'Connecting to %s:%d...' % (self.host, self.port)
        node = NodeServer(self.name, self.host, self.port)
        node.onStartup().addErrback(self._error)
        node.onShutdown().addCallbacks(self._disconnected, self._error)
        self.cxn = TCPClient(self.host, self.port, node)
        self.addService(self.cxn)

    def _disconnected(self, data):
        log.msg('Node disconnected from manager.')
        return self._reconnect()

    def _error(self, failure):
        log.msg(failure.getErrorMessage())
        return self._reconnect()

    def _reconnect(self):
        if hasattr(self, 'cxn'):
            self.removeService(self.cxn)
            del self.cxn
        reactor.callLater(self.reconnectDelay, self.startConnection)
        print 'Will try to reconnect in %d seconds...' % self.reconnectDelay

class NodeConfig(object):
    def __init__(self, registry, nodename, dirs, mods):
        self.registry = registry
        self.nodename = nodename
        self.dirs = dirs
        self.mods = mods
        
    @classmethod
    @inlineCallbacks
    def load(cls, registry, nodename='__default__', create=False):
        p = registry.packet()
        p.cd(['', 'Nodes', nodename], create)
        if create:
            p.set('directories', [])
            p.set('packages', ['labrad.servers'])
        p.get('directories', key='dirs')
        p.get('packages', key='mods')
        resp = yield p.send()
        returnValue(cls(registry, nodename, resp.dirs, resp.mods))
        
    @inlineCallbacks
    def save(self, nodename=None):
        if nodename is None:
            nodename = self.nodename
        p = self.registry.packet()
        p.cd(['', 'Nodes', nodename], True)
        p.set('directories', self.dirs)
        p.set('packages', self.mods)
        yield p.send()


class NodeServer(LabradServer):
    name = 'node %LABRADNODE%'

    def __init__(self, nodename, host, port):
        LabradServer.__init__(self)
        self.nodename = nodename
        self.name = 'node %s' % nodename
        self.host = host
        self.port = port

    @inlineCallbacks
    def initServer(self):
        self.servers = {}
        self.runners = {}
        self.initMessages()
        yield self.refreshServers()
        
    def initMessages(self):
        """Set up messages to be dispatched locally and sent out over LabRAD."""
        # set up messages to be relayed out over LabRAD
        def _relayMessage(self, signal, sender, **kw):
            kw['node'] = self.name
            self.client.manager.send_named_message('node.' + signal, tuple(kw.items()))
        messages = ['server_starting', 'server_started',
                    'server_stopping', 'server_stopped']
        for message in messages:
            dispatcher.connect(_relayMessage, message)
            
        # set up message handlers for subprocess
        dispatcher.connect(self.subprocessStarted, 'server_started')
        dispatcher.connect(self.subprocessStopped, 'server_stopped')

    @inlineCallbacks
    def loadConfig(self):
        """Load configuration for this node from the registry."""
        reg = self.client.registry
        p = reg.packet()
        p.cd(['', 'Nodes'], True)
        p.dir()
        resp = yield p.send()
        dirs, keys = resp.dir
        if self.nodename not in dirs:
            config = yield NodeConfig.load(reg, create=('__default__' not in dirs))
            config.save(self.nodename)
        else:
            config = yield NodeConfig.load(reg, self.nodename)
        # filter gets rid of empty strings
        self.serverMods = filter(None, config.mods)
        self.serverDirs = filter(None, config.dirs)

    def refreshServers(self):
        """Refresh the list of available servers."""
        def finishRefresh(result):
            del self._onRefresh
            return result
        if not hasattr(self, 'onRefresh'):
            self._onRefresh = util.DeferredSignal()
            d = self._doRefresh()
            d.addBoth(finishRefresh)
            d.chainDeferred(self._onRefresh)
        return self.onRefresh()
            
    @inlineCallbacks
    def _doRefresh(self):
        found = {}

        # refresh list of directories to search
        yield self.loadConfig()

        # look for python plugins
        for module in self.serverMods:
            try:
                __import__(module)
                for plugin in getPlugins(ILabradServer, sys.modules[module]):
                    p = createPythonServerCls(plugin)
                    p.client = self.client
                    if p.name not in found:
                        found[p.name] = p
            except Exception, e:
                print e

        # look for .ini files
        for dirname in self.serverDirs:
            for path, dirs, files in os.walk(dirname):
                for f in files:
                    if not f.lower().endswith('.ini'):
                        continue
                    try:
                        p = createGenericServerCls(path, f)
                        p.client = self.client
                        if p.name not in found:
                            found[p.name] = p
                    except Exception, e:
                        print e

        # add new servers and remove old ones
        self.servers.update(found)
        for name in self.servers:
            if name not in found:
                del self.servers[name]

    def initContext(self, c):
        c['environ'] = {}
        
    def serverConnected(self, ID, name):
        """Called when a server connects to LabRAD."""
        dispatcher.send('serverConnected', ID=ID, name=name)
        
    def subprocessStarted(self, sender):
        """Called when a subprocess successfully connects."""
        self.runners[sender.name] = sender

    def subprocessStopped(self, sender):
        """Called when a subprocess successfully disconnects."""
        del self.runners[sender.name]
        
    def stopServer(self):
        """Stop this node by killing all subprocesses."""
        stoppages = [srv.stop() for srv in self.runners.values()]
        return defer.DeferredList(stoppages)
        
    @setting(1, name=['s'], environ=['*(ss)'], returns=['s'])
    def start(self, c, name, environ={}):
        """Start an instance of a server."""
        env = dict(c['environ']) # copy context environment
        env.update(environ)
        environ.update(LABRADNODE=self.nodename,
                       LABRADHOST=self.host,
                       LABRADPORT=str(self.port),
                       LABRADPASSWORD=self.password)
        
        if name not in self.servers:
            raise Exception("Unknown server: '%s'." % name)
        srv = self.servers[name](environ)
        yield srv.start()
        returnValue(srv.name)

    @setting(2, name=['s'], returns=['s'])
    def stop(self, c, name):
        """Stop a running server instance."""
        if name not in self.runners:
            raise Exception("'%s' is not running." % name)
        srv = self.runners[name]
        yield srv.stop()
        returnValue(srv.name)

    @setting(3, name=['s'], returns=['s'])
    def restart(self, c, name):
        """Restart a running server instance."""
        if name not in self.runners:
            raise Exception("'%s' is not running." % name)
        srv = self.runners[name]
        yield srv.restart()
        returnValue(srv.name)

    @setting(10, returns=['*s'])
    def available_servers(self, c):
        """Get a list of available servers."""
        return sorted(self.servers.keys())

    @setting(11, returns=['*(ss)'])
    def running_servers(self, c):
        """Get a list of running server instances.

        Returns a list of tuples of server name and instance name.
        """
        return sorted((s.__class__.name, n) for n, s in self.runners.items())

    @setting(12, returns=['*s'])
    def local_servers(self, c):
        """Get a list of local servers."""
        return sorted(n for n, s in self.servers.items() if s.isLocal)

    @setting(13, returns=[''])
    def refresh_servers(self, c):
        """Refresh the list of available servers."""
        yield self.refreshServers()

    @setting(14, returns=['*(s{name} s{desc} s{ver} s{instname} *s{vars} *s{running})'])
    def servers_info(self, c):
        """Get information about all servers on this node."""
        def info(name, cls):
            instances = [n for n, s in self.runners.items()
                                    if s.__class__.name == name]
            return (name, cls.__doc__ or '', cls.version,
                    cls.instancename, cls.environVars, instances)
        return [info(*item) for item in sorted(self.servers.items())]

    @setting(20, returns=['*(ss)'])
    def environ(self, c):
        """Get a list of environment variables set in this context."""
        env = c.setdefault('environ', {})
        return sorted(env.items())

    @setting(21, items=['(ss)', '*(ss)'], returns=['*(ss)'])
    def environ_set(self, c, items):
        """Set environment variables in this context."""
        if isinstance(items, tuple):
            items = [items]
        env = c['environ']
        for key, value in items:
            env[key.upper()] = value
        return sorted(env.items())

    @setting(22, keys=['s', '*s'], returns=['*(ss)'])
    def environ_del(self, c, keys):
        """Delete environment variables in this context."""
        if isinstance(keys, str):
            keys = [keys]
        env = c['environ']
        for key in keys:
            del env[key.upper()]
        return sorted(env.items())

    @setting(40, returns=['*s'])
    def path(self, c):
        """Get a list of directories that will be searched for servers."""
        return self.serverDirs

    @setting(41, dirs=['s', '*s'], returns=['*s'])
    def path_add(self, c, dirs):
        """Add directories to the server search path."""
        if isinstance(dirs, str):
            dirs = [dirs]
        for d in dirs:
            if d not in self.serverDirs:
                self.serverDirs.append(d)
        return self.serverDirs

    @setting(42, dirs=['s', '*s'], returns=['*s'])
    def path_remove(self, c, dirs):
        """Remove directories from the server search path."""
        if isinstance(dirs, str):
            dirs = [dirs]
        for d in dirs:
            self.serverDirs.remove(d)
        return self.serverDirs

    @setting(45, returns=['*s'])
    def modules(self, c):
        """Get a list of python modules that will be searched for servers."""
        return self.serverMods

    @setting(46, mods=['s', '*s'], returns=['*s'])
    def module_add(self, c, mods):
        """Add python modules to be searched for servers."""
        if isinstance(mods, str):
            mods = [mods]
        for m in mods:
            if m not in self.serverMods:
                __import__(m)
                self.serverMods.append(m)
        return self.serverMods

    @setting(47, mods=['s', '*s'], returns=['*s'])
    def module_remove(self, c, mods):
        """Remove python modules from the server search path."""
        if isinstance(mods, str):
            mods = [mods]
        for m in mods:
            self.serverMods.remove(m)
        return self.serverMods

    @setting(100, name=['s'], returns=['*(ts)'])
    def server_output(self, c, name):
        """Get output from a server's stdout."""
        if name not in self.runners:
            raise Exception("'%s' is not running." % name)
        return self.runners[name].output

    @setting(101, name=['s'], returns=[''])
    def clear_output(self, c, name):
        """Clear the stdout buffer of a server."""
        if name not in self.runners:
            raise Exception("'%s' is not running." % name)
        self.runners[name].clearOutput()

    @setting(102, name=['s'], returns=['s'])
    def server_version(self, c, name):
        """Get version information for a server."""
        if name not in self.servers:
            raise Exception("'%s' not found." % name)
        return self.servers[name].version
    
    @setting(1000, returns=['*(ss)'])
    def node_version(self, c):
        """Return a list of key-value tuples containing info about this node."""
        import socket, sys
        info = {'hostname': socket.gethostname(),
                'python version': sys.version,
                'labrad version': labrad.__version__,
                'labrad revision': labrad.__revision__,
                'labrad date': labrad.__date__}
        return list(info.items())
