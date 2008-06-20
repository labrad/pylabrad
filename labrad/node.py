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
        print "spawning process..."
        print "path:", self.path
        print "executable:", self.executable
        print "args:", self.args

        startd = self.startup()
        self.starting = True
        dispatcher.connect(self.serverConnected, "serverConnected")
        dispatcher.send("server_starting", server=self.name)
        self.proc = reactor.spawnProcess(self, self.executable, self.args,
                                         env=self.env, path=self.path)
        timeoutCall = reactor.callLater(self.timeout, self.kill)
        try:
            yield startd
            dispatcher.send("server_started", server=self.name)
        finally:
            self.starting = False
            if timeoutCall.active():
                timeoutCall.cancel()
            dispatcher.disconnect(self.serverConnected, "serverConnected")
        
    @inlineCallbacks
    def restart(self):
        yield self.stop()
        yield self.start()

    @inlineCallbacks
    def stop(self):
        if not self.running:
            return
        print "stopping '%s'..." % self.name
        dispatcher.send("server_stopping", server=self.name)
        d = self.shutdown()
        self.kill()
        yield d
        dispatcher.send("server_stopped", server=self.name)

    def kill(self):
        try:
            #self.proc.writeToChild(0, '\x03')
            self.proc.signalProcess("KILL")
            #self.client._cxn.sendMessage(self.ID, [(987654321, None)])
        except:
            pass

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

    def serverConnected(self, ID, name):
        print 'server connected:', name
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
    environVars = findEnvironmentVars(cls.instancename)
    cls.isLocal = len(environVars) > 0

    # startup
    cls.cmdline = scp.get('startup', 'cmdline', raw=True)
    cls.path = path
    try:
        cls.timeout = scp.getint('startup', 'timeout')
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
    environVars = findEnvironmentVars(cls.instancename)
    cls.isLocal = len(environVars) > 0
    
    # startup
    cls.cmdline = ' '.join([sys.executable, '-m', plugin.__module__])
    cls.path = os.path.split(sys.modules[plugin.__module__].__file__)[0]
    return cls

def getNodeConfig(nodename=None):
    try:
        conf = ConfigFile('node')
    except:
        conf = ConfigFile('node-template')
    if conf.has_section(nodename):
        section = nodename
    else:
        section = 'default'
    # filter gets rid of empty strings
    parse = lambda string: filter(None, [s.strip() for s in string.split(';')])
    mods = parse(conf.get(section, 'modules'))
    dirs = parse(conf.get(section, 'directories'))
    return mods, dirs

class IProcNode(Interface):
    pass

class ProcNode(MultiService):
    implements(IProcNode)

    reconnectDelay = 10

    def __init__(self, nodename, host, port):
        MultiService.__init__(self)
        self.nodename = nodename
        self.host = host
        self.port = port
        self.name = 'node %s' % nodename

        self.servers = {}
        self.runners = {}
        self.cxn = None

        self.serverMods, self.serverDirs = getNodeConfig()

    def startService(self):
        MultiService.startService(self)
        self.startConnection()

    def stopService(self):
        return self.stopAll()

    def startConnection(self):
        print 'connecting to %s:%d...' % (self.host, self.port)
        srv = ILabradServer(self)
        d = srv.onStartup()
        d.addCallback(self._connected, srv)
        d.addErrback(self._error)
        d = srv.onShutdown()
        d.addCallbacks(self._disconnect, self._error)
        self.cxn = TCPClient(self.host, self.port, srv)
        self.addService(self.cxn)

    def _connected(self, data, srv):
        self.client = srv.client
        self.manager = srv.client.manager
        self.password = srv.password
        self.refresh_servers()

    def _disconnect(self, data):
        log.msg('Node disconnected from manager.')
        return self._reconnect()

    def _error(self, failure):
        log.msg(failure.getErrorMessage())
        return self._reconnect()

    def _reconnect(self):
        stopAll = self.stopAll()
        if self.cxn is not None:
            self.removeService(self.cxn)
            self.cxn = None
        reactor.callLater(self.reconnectDelay, self.startConnection)
        print 'Will try to reconnect in %d seconds...' % self.reconnectDelay
        return stopAll

    def refresh_servers(self):
        """Refresh the list of available servers."""
        found = {}

        # refresh list of directories to search
        self.serverMods, self.serverDirs = getNodeConfig()

        # look for python plugins
        for module in self.serverMods:
            try:
                __import__(module)
                for plugin in getPlugins(ILabradServer, sys.modules[module]):
                    p = createPythonServerCls(plugin)
                    p.manager = self.manager
                    p.client = self.client
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
                        p.manager = self.manager
                        p.client = self.client
                        found[p.name] = p
                    except Exception, e:
                        print e

        # add new servers to list
        self.servers.update(found)

        # delete servers that are no longer found
        deletions = [name for name in self.servers if name not in found]
        for name in deletions:
            del self.servers[name]

    def stopAll(self):
        # stop any running servers
        stoppages = [srv.stop() for srv in self.runners.values()]
        return defer.DeferredList(stoppages)

    @inlineCallbacks
    def start(self, name, environ={}):
        """Start an instance of a server."""
        try:
            cls = self.servers[name]
        except KeyError:
            raise Exception("Unknown server: '%s'." % name)

        # the environment can be overridden in this context or this request
        environ.update(LABRADNODE=self.nodename,
                       LABRADHOST=self.host,
                       LABRADPORT=str(self.port),
                       LABRADPASSWORD=self.password)

        srv = cls(environ)
        srv.startup.connect(self.serverStarted)
        srv.shutdown.connect(self.serverStopped)
        yield srv.start()
        returnValue(srv.name)

    def serverStarted(self, srv):
        self.runners[srv.name] = srv

    def serverStopped(self, srv):
        del self.runners[srv.name]

    @inlineCallbacks
    def stop(self, name):
        """Stop a running server instance."""
        try:
            srv = self.runners[name]
        except KeyError:
            raise Exception("'%s' is not running." % name)
        yield srv.stop()
        returnValue(srv.name)

    @inlineCallbacks
    def restart(self, name):
        """Restart a running server instance."""
        try:
            srv = self.runners[name]
        except KeyError:
            raise Exception("'%s' is not running." % name)
        yield srv.restart()
        returnValue(srv.name)

    def available_servers(self):
        """Get a list of available servers."""
        return sorted(self.servers.keys())

    def servers_info(self):
        slist = []
        for name, cls in sorted(self.servers.items()):
            instances = [n for n, s in self.runners.items()
                                    if s.__class__.name == name]
            info = (name, cls.__doc__ or '', cls.version,
                    cls.instancename, cls.isLocal, instances)
            slist.append(info)
        return slist

    def running_servers(self):
        """Get a list of running server instances.

        Returns a list of tuples of server name and instance name.
        """
        return sorted((s.__class__.name, n) for n, s in self.runners.items())

    def local_servers(self):
        """Get a list of local servers."""
        return sorted(n for n, s in self.servers.items() if s.isLocal)

    def server_output(self, name):
        try:
            srv = self.runners[name]
        except KeyError:
            raise Exception("'%s' is not running." % name)
        return srv.output

    def clear_output(self, name):
        try:
            srv = self.runners[name]
        except KeyError:
            raise Exception("'%s' is not running." % name)
        srv.clearOutput()

    def server_version(self, name):
        try:
            srv = self.servers[name]
        except KeyError:
            raise Exception("'%s' not found." % name)
        return srv.version

class ProcNodeServer(LabradServer):
    def __init__(self, node):
        self.node = node
        self.name = node.name
        LabradServer.__init__(self)

    def initServer(self):
        # set up message relaying so other clients can
        # keep track of what happens on this node
        messages = ["server_starting", "server_started",
                    "server_stopping", "server_stopped"]
        for message in messages:
            dispatcher.connect(self._relayMessage, message)

    def _relayMessage(self, signal, sender, **kw):
        """Relay a locally-dispatched message out over LabRAD."""
        kw['node'] = self.name
        self.client.manager.send_named_message("node." + signal, tuple(kw.items()))

    def initContext(self, c):
        c['environ'] = {}
        
    def serverConnected(self, ID, name):
        dispatcher.send("serverConnected", ID=ID, name=name)
        
    @setting(1, name=['s'], environ=['*(ss)'], returns=['s'])
    def start(self, c, name, environ={}):
        """Start an instance of a server."""
        env = dict(c['environ']) # copy context environment
        env.update(environ)
        return self.node.start(name, env)

    @setting(2, name=['s'], returns=['s'])
    def stop(self, c, name):
        """Stop a running server instance."""
        return self.node.stop(name)

    @setting(3, name=['s'], returns=['s'])
    def restart(self, c, name):
        """Restart a running server instance."""
        return self.node.restart(name)

    @setting(10, returns=['*s'])
    def available_servers(self, c):
        """Get a list of available servers."""
        return self.node.available_servers()

    @setting(11, returns=['*(ss)'])
    def running_servers(self, c):
        """Get a list of running server instances.

        Returns a list of tuples of server name and instance name.
        """
        return self.node.running_servers()

    @setting(12, returns=['*s'])
    def local_servers(self, c):
        """Get a list of local servers."""
        return self.node.local_servers()

    @setting(13, returns=[''])
    def refresh_servers(self, c):
        """Refresh the list of available servers."""
        self.node.refresh_servers()

    @setting(14, returns=['*(s{name} s{desc} s{ver} s{instname} b *s{running})'])
    def servers_info(self, c):
        """Get information about all servers on this node."""
        #print self.node.servers_info()
        return self.node.servers_info()

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

    @property
    def serverDirs(self):
        return self.node.serverDirs

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

    @property
    def serverMods(self):
        return self.node.serverMods

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
        return self.node.server_output(name)

    @setting(101, name=['s'], returns=[''])
    def clear_output(self, c, name):
        """Clear the stdout buffer of a server."""
        self.node.clear_output(name)

    @setting(102, name=['s'], returns=['s'])
    def server_version(self, c, name):
        """Get version information for a server."""
        return self.node.server_version(name)
    
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

registerAdapter(ProcNodeServer, IProcNode, ILabradServer)

