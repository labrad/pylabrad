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
labrad.server

Base classes for building asynchronous, context- and request- aware
servers with labrad.
"""

import copy
import getpass
from datetime import datetime

from twisted.application import service, internet
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import failure, log
from twisted.python.components import registerAdapter
from twisted.plugin import IPlugin
from zope.interface import Interface, Attribute, implements

from labrad import util, constants as C, types as T, errors
from labrad.decorators import setting
from labrad.protocol import LabradProtocol, LabradClient
from labrad.interfaces import ILabradServer, IClientAsync

class ServerProtocol(LabradProtocol):
    """Standard protocol for labrad servers.

    Most of the server-specific customization goes in the factory,
    not this protocol class.
    """
    def __init__(self):
        LabradProtocol.__init__(self)
        self.queues = {}

    def requestReceived(self, source, context, request, records):
        """Handle incoming requests."""
        if not self.factory.serving:
            return
        if any(isinstance(data, Exception) for ID, data in records):
            log.msg('Error in incoming request: %s, %s, %s, %s' %\
                    (source, context, request, records))
            return
        q = self.queues.get(context, None)
        if q is None:
            # create a new queue for contexts we have not yet seen
            q = self.queues[context] = defer.DeferredQueue()
            q.alive = True
            serveLoop = self.serveContext(context, q)
            serveLoop.addErrback(self._contextFailed, context)
        q.put((source, request, records))

    def _contextFailed(self, failure, context):
        """Error handler to catch failure of a context serve loop.
        
        If we ever get here, something has gone very wrong.
        """
        log.err('Unhandled exception while serving context %s.' % (context,))
        log.err(failure)
        del self.queues[context]

    @inlineCallbacks
    def serveContext(self, context, queue):
        """A generator to serve a single context.

        This generator should run forever, taking packets from the
        input queue for this context and serving up the request.
        """
        ctxtData = yield self.factory.newContext(context)
        yield self.factory.initContext(ctxtData)
        queue.ctxtData = ctxtData
        while queue.alive:
            source, request, records = yield queue.get()
            if queue.alive:
                try:
                    yield self.serveRequest(source, context, request,
                                            records, queue)
                except:
                    log.err("Unhandled exception while serving request: " \
                            "source: %s, context: %s, request: %s, " \
                            "records: %s, ctxtData: %s" % \
                            (source, context, request, records, ctxtData))
                    log.err()
            else:
                self.expireRequest(source, context, request)
        # now that this context is dead, cancel any pending requests
        for source, request, records in queue.pending:
            self.expireRequest(source, context, request)

    def handleExpiration(self, data):
        """Context expiration handler.
        
        This gets called by the manager either with a single word,
        to expire all contexts with that high word, or with a tuple
        of high word, low word, to expire just that context.
        """
        if isinstance(data, tuple):
            self.expireContext(data)
        else:
            self.factory.pruneSignals(data)
            self.expireAllContexts(data)

    def expireContext(self, context):
        """Expire a single context."""
        if context in self.queues:
            q = self.queues[context]
            q.alive = False
            q.put((None, None, None)) # put a dummy request to kill the serveLoop
            self.factory.expireContext(q.ctxtData)
            del self.queues[context]

    def expireAllContexts(self, ID):
        """Expire all contexts with a given ID (high word)."""
        for context in self.queues.keys():
            if context[0] == ID:
                self.expireContext(context)

    def expireRequest(self, source, context, request):
        """Expire a pending request."""
        # TODO: determine if anything needs to be sent here

    @inlineCallbacks
    def serveRequest(self, source, context, request, records, queue):
        """A generator to serve a single request.

        We iterate over the records in this packet, passing them on to
        the appropriate handlers.  Each handler is a generator, possibly
        passing back multiple values.  If a handler returns a deferred,
        we wait for it to fire and then send the result back into the
        handler.  The data returned by the handler is collected and sent
        back to the source of the request.
        """
        replies = []
        ctxtData = queue.ctxtData
        ctxtData.source = source
        try:
            for ID, data in records:
                result, returns = self.factory.callHandler(ID, ctxtData, data)

                # wait for a deferred result to finish
                if isinstance(result, defer.Deferred):
                    result = yield result

                # append result to replies, with hints about return type
                replies.append((ID, result, returns))
        except Exception, e:
            replies.append((ID, self.getTraceback(e)))
        if queue.alive:
            try:
                self.sendPacket(source, context, -request, replies)
            except Exception, e:
                # if an error occurs in flattening, send so client doesn't hang
                # TODO: make the message more helpful (indicate server problem)
                self.sendPacket(source, context, -request, [(ID, e)])
        else:
            self.expireRequest(source, context, request)

    def getTraceback(self, e):
        code = getattr(e, 'code', 0)
        if self.factory.sendTracebacks:
            f = failure.Failure()
            tb = f.getTraceback(elideFrameworkCode=True)
            msg = 'Remote %s' % tb
        else:
            msg = getattr(e, 'msg', str(e))
        msg = '[%s] %s' % (self.factory.name, msg)
        return T.Error(msg, code)

class Signal(object):
    """A Signal object is a simple publish/subscribe messaging primiive.
    
    Servers expose signals as settings that clients or other servers can
    make requests to.  A request allows the client or server to sign up to
    receive messages when this signal is fired.  All the details of managing
    who is listening for these signals is handled here, so the application
    does not need to worry about it.
    """
    def __init__(self, ID, name, tag):
        self.ID = ID
        self.name = name
        self.tag = tag
        self.listeners = {}

    def __call__(self, data, contexts=None):
        """Fire a message with the given data to all connected listeners."""
        # TODO: remove listeners when clients disconnect
        if hasattr(self, 'parent'):
            cxn = self.parent._cxn
            if contexts is None:
                # send this to everyone
                for context, targets in self.listeners.items():
                    for target, ID in targets.items():
                        cxn.sendMessage(target, [(ID, data)], context)
            else:
                # send only to those in the specified
                # context or list of contexts
                if isinstance(contexts, tuple) and len(contexts) \
                   and not isinstance(contexts[0], tuple):
                    contexts = [contexts]
                for context in contexts:
                    if context not in self.listeners:
                        continue
                    for target, ID in self.listeners[context].items():
                        cxn.sendMessage(target, [(ID, data)], context)
            
    def connect(self, context, target, ID):
        """Connect a listener to this signal.
        
        Connections are made to a given target/message ID, in a particular
        context.  When the signal is fired later, it can be fired to all listeners,
        or only to those listeners signed up in particular contexts.
        """
        # TODO: use weak references here to prevent memory leaks
        cdict = self.listeners.setdefault(context, {})
        tdict = cdict.setdefault(target, ID)
        
    def disconnect(self, context, target):
        """Disconnect a listener from this signal."""
        if context in self.listeners:
            cdict = self.listeners[context]
            if target in cdict:
                del cdict[target]
                
    def disconnectAll(self, target):
        """Disconnect all listeners pointing at a particular target."""
        for context in self.listeners:
            cdict = self.listeners[context]
            if target in cdict:
                del cdict[target]

class LabradServer(LabradClient):
    """A generic LabRAD server."""

    implements(IPlugin, ILabradServer)

    protocol = ServerProtocol
    sendTracebacks = True

    def __init__(self):
        self.started = False
        self.onStartup = util.DeferredSignal()
        self.onShutdown = util.DeferredSignal()
        
        self.serving = False
        self.settingMap = {}
        self.initSignals()
        self.initSettings()
        self._serverNames = {}

    # Initialization
    # these functions happen behind the scenes to prepare the server
    def initSignals(self):
        """Initialize all signals for this server."""
        for methodName in dir(self):
            sig = getattr(self, methodName)
            if isinstance(sig, Signal):
                self.createSignalHandler(sig)
                sig.parent = self

    def createSignalHandler(self, sig):
        """Create a handler for signal connection/disconnection."""
        @setting(sig.ID, sig.name, ID=['w'], returns=[''])
        def handler(self, c, ID=None):
            if ID is None:
                sig.disconnect(c.ID, c.source)
            else:
                sig.connect(c.ID, c.source, ID)
        handler.__doc__ = """Connect to/Disconnect from signal '%s'
        
        Passing a word ID will cause messages to be sent to setting ID
        when this signal is fired.  Passing nothing will cancel future messages.
        The message data will be of type '%s'.""" % (sig.name, sig.tag)
        setattr(self, '_signal_' + sig.name, handler)
        
    def pruneSignals(self, ID):
        """Disconnect all signals from a particular target ID.
        
        This is called automatically whenever a server disconnects.
        """
        for methodName in dir(self):
            sig = getattr(self, methodName)
            if isinstance(sig, Signal):
                sig.disconnectAll(ID)
    
    def initSettings(self):
        """Initialize all settings for this server."""
        self.settings = {}
        for methodName in dir(self):
            setting = getattr(self, methodName)
            if hasattr(setting, 'isSetting'):
                self.registerSetting(setting)

    def registerSetting(self, s):
        name, ID = self.settingMap.get(s.name, (s.name, s.ID))
        self._checkDuplicates(s, name, ID)
        self.settings[ID] = name, s

    def _checkDuplicates(self, s, name, ID):
        """Check whether a setting conflicts with previously-registered settings."""
        for oldID, (oldName, oldS) in self.settings.items():
            if ID == oldID or name == oldName:
                msg = "Duplicate settings. New: '%s' (%d), Old: '%s' (%d)" % \
                      (name, ID, oldName, oldID)
                raise AssertionError(msg)

    def settingInfo(self, s):
        """Get info about a setting suitable for passing to the manager."""
        name, ID = self.settingMap.get(s.name, (s.name, s.ID))
        descr, notes = util.parseSettingDoc(s.__doc__)
        return long(ID), name, descr, s.accepts, s.returns, notes
        
    # Login information
    def getIdentification(self):
        descr, notes = util.parseSettingDoc(self.__doc__)
        return self.name, descr, notes
        
    # Network events
    # these methods are called by network events from twisted
    @inlineCallbacks
    def loginSucceeded(self, message):
        """Called after we've authenticated with the labrad manager.

        After authorization, we do several things:

           1. Register all server settings
           2. Call "initServer" to do more specific initialization
           3. Start the server loop

        If any of these steps fail, the server will disconnect.
        """
        log.msg('%s starting...' % self.name)
        log.msg('connected to %s:%s' % (self.mgr_host, self.mgr_port))
        # initialize client connection wrapper
        mgr = self.client.manager

        # register settings
        p = mgr.packet()
        for ID, (name, setting) in sorted(self.settings.items()):
            p.s__register_setting(self.settingInfo(setting))
        yield p.send()

        # do server-specific initialization
        yield self.initServer()
        reactor.addSystemEventTrigger('before', 'shutdown',
                                      self.stopServer)
        # kill me with a message, so that clean-up happens nicely
        self._cxn.addListener(987654321, lambda _: reactor.stop())
        self.serving = True
        
        # sign up for notifications when servers connect and disconnect
        yield mgr.notify_on_connect.connect(self._serverConnected)
        yield mgr.notify_on_disconnect.connect(self._serverDisconnected)
        yield mgr.s__notify_on_context_expiration.connect(
                  self._cxn.handleExpiration, signupargs=(True,))
        self._serverNames.update((yield mgr.servers()))
        
        # let the rest of the world know we're ready
        yield mgr.s__start_serving()
        log.msg('%s now serving' % self.name)
    
    def callHandler(self, ID, ctxtData, data):
        """Call a setting handler in context."""
        name, setting = self.settings[ID]
        result = setting.unpack(self, ctxtData, data)
        return result, setting.returns
    
    def disconnect(self, error=None):
        if error:
            self._error = failure.Failure(error)
        self._cxn.disconnect()
    
        
    # Server startup and shutdown
    # these methods should be overridden
    def initServer(self):
        """Initialize Server.

        Called after registering settings and creating a client
        connection to labrad, but before we start serving requests.
        """

    def stopServer(self):
        """Stop the server.

        Called when the server is shutting down, but before we have
        closed any client connections.  Perform any cleanup operations here.
        """
    
    # Manager notifications
    # these methods should not be overridden
    def _serverConnected(self, data):
        """Handle connection messages from the manager."""
        ID, name = data
        self._serverNames[ID] = name
        self.serverConnected(ID, name)
    
    def _serverDisconnected(self, data):
        """Handle disconnection messages from the manager."""
        ID = data
        self.pruneSignals(ID)
        if ID in self._serverNames:
            name = self._serverNames[ID]
            self.serverDisconnected(ID, name)
        else:
            self.serverDisconnected(ID, '<unknown>')
    
    # these methods should be overridden
    def serverConnected(self, ID, name):
        """Called when a new server connects to labrad."""
        
    def serverDisconnected(self, ID, name):
        """Called when a server disconnects from labrad."""
    
    
    # Context handling
    # these methods should be overridden
    def newContext(self, ID):
        """Create a new context object."""
        c = util.ContextDict()
        c.ID = ID
        return c
        
    def initContext(self, c):
        """Initialize a new context object."""
        
    def expireContext(self, c):
        """Expire Context.

        Called when a client which created a context disconnects.
        Any cleanup operations on the context should be done here.
        """

        
    # Handlers
    # these handle remotely-accessible settings
    @setting(11111111)
    def echo(self, c, data):
        """Echo any packet."""
        return data

    @setting(12121212, returns=['s'])
    def debug(self, c, data):
        """Get a __repr__ of the current context."""
        return repr(c)
        
        
    # Signals
    # these expose asynchronous signals, with a signup mechanism
    # do this (no customization)
    onLog = Signal(13131313, 'signal: log', 't*s')
    
    def log(self, *messages):
        self.onLog((datetime.now(), messages))
    
    # or this (simple filtering, change call signature)
    #@signal(13131313, 'Log', returns=['t*s'])
    #def log(self, *messages):
    #    return datetime.now(), messages
    
    # or this (completely customizable, including signup customization)
    #class Log(Signal):
    #    def connect():
    #        pass
    #        
    #    def disconnect():
    #        pass
    #        
    #    def __call__():
    #        pass
            

class LabradService(internet.TCPClient):
    def __init__(self, server):
        internet.TCPClient.__init__(self, server.host, server.port, server)
        self.setName(server.name)
        self.onStartup = server.onStartup
        self.onShutdown = server.onShutdown

registerAdapter(LabradService, ILabradServer, service.IService)


