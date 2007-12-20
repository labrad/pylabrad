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
labrad.procnode

Provides an interface to manage all python labrad servers
running on a particular computer.  This version runs each
server in a separate process, so that they can not interfere
with each other.
"""

import os
import re
import sys
from datetime import datetime
from ConfigParser import SafeConfigParser

from labrad import util
from labrad.config import ConfigFile
from labrad.server import ILabradServer, LabradServer, setting

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

defer.setDebugging(True)

def findEnvironmentVars(string):
    return re.findall('%([^%]+)%', string)

def interpEnvironmentVars(string, env):
    labels = findEnvironmentVars(string)
    for label in labels:
        tag = '%' + label + '%'
        string = string.replace(tag, env[label.upper()])
    return string

class ServerProcess(ProcessProtocol):
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

        mgr = self.manager
        yield mgr.notify_on_connect.connect(self.serverConnected)

        print "starting '%s'..." % self.name
        print "spawning process..."
        print "env:", self.env
        print "path:", self.path
        print "executable:", self.executable
        print "args:", self.args

        startd = self.startup()
        self.starting = True
        self.proc = reactor.spawnProcess(self, self.executable, self.args,
                                         env=self.env, path=self.path)
        timeoutCall = reactor.callLater(self.timeout, self.kill)
        try:
            yield startd
        finally:
            self.starting = False
            if timeoutCall.active():
                timeoutCall.cancel()
            yield mgr.notify_on_connect.disconnect(self.serverConnected)

    @inlineCallbacks
    def restart(self):
        yield self.stop()
        yield self.start()

    def stop(self):
        if not self.running:
            return defer.succeed(None)
        print "stopping '%s'..." % self.name
        d = self.shutdown()
        self.kill()
        return d

    def kill(self):
        try:
            self.proc.signalProcess('KILL')
        except:
            pass

    def outReceived(self, data):
        self.output.append((datetime.now(), data))
        print "'%s' stdout: %s" % (self.name, data)

    def errReceived(self, data):
        self.output.append((datetime.now(), data))
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

    def serverConnected(self, data):
        ID, name = data
        print 'server connected:', name
        if name == self.name:
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
    cls.isLocal = hasattr(plugin, 'isLocal')
    if cls.isLocal:
        cls.instancename = ' '.join(['%LABRADNODE%', cls.name])
    else:
        cls.instancename = cls.name
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

def traceCall(result, msg):
    print msg, result
    return result

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
        d = srv.startup()
        d.addCallback(self._connected, srv)
        d.addErrback(self._error)
        d = srv.shutdown()
        d.addCallbacks(self._disconnect, self._error)
        self.cxn = TCPClient(self.host, self.port, srv)
        self.addService(self.cxn)

    def _connected(self, data, srv):
        self.manager = srv.client.manager
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

        # look for python plugins
        for module in self.serverMods:
            try:
                __import__(module)
                for plugin in getPlugins(ILabradServer, sys.modules[module]):
                    p = createPythonServerCls(plugin)
                    p.manager = self.manager
                    found[p.name] = p
            except Exception, e:
                print e

        # look for .ini files
        for dirname in self.serverDirs:
            for path, dirs, files in os.walk(dirname):
                for f in files:
                    if not f.endswith('.ini'):
                        continue
                    try:
                        p = createGenericServerCls(path, f)
                        p.manager = self.manager
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
                       LABRADPORT=str(self.port))

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

class ProcNodeServer(LabradServer):
    def __init__(self, node):
        self.node = node
        self.name = node.name
        LabradServer.__init__(self)

    @setting(1, name=['s'], environ=['*(ss)'], returns=['s'])
    def start(self, c, name, environ={}):
        """Start an instance of a server."""
        env = c.setdefault('environ', {})
        env.update(environ)
        env.update(LABRADPASSWORD=self.password)
        return self.node.start(name, env)

    @setting(2, name=['s'], returns=[''])
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

    @setting(20, returns=['*(ss)'])
    def environ(self, c):
        """Get a list of environment variables set in this context."""
        env = c.setdefault('environ', {})
        return sorted(env.items())

    @setting(21, items=['(ss)', '*(ss)'], returns=['*(ss)'])
    def environ_set(self, c, items):
        """Set an environment variable in this context."""
        if isinstance(items, tuple):
            items = [items]
        for key, value in items:
            if key.upper() in self.environ:
                raise Exception("Key '%s' is protected." % key)
            env = c.setdefault('environ', {})
            env[key.upper()] = value
        return sorted(env.items())

    @setting(22, keys=['s', '*s'], returns=['*(ss)'])
    def environ_del(self, c, keys):
        """Delete and environment variable in this context."""
        if isinstance(keys, str):
            keys = [keys]
        env = c.setdefault('environ', {})
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

    @setting(50, returns=[''])
    def refresh_servers(self, c):
        """Refresh the list of available servers."""
        self.node.refresh_servers()

    @setting(100, name=['s'], returns=['*(ts)'])
    def server_output(self, c, name):
        return self.node.server_output(name)

    @setting(101, name=['s'], returns=[''])
    def clear_output(self, c, name):
        self.node.clear_output(name)

registerAdapter(ProcNodeServer, IProcNode, ILabradServer)

