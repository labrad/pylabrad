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

from datetime import datetime
from operator import attrgetter
import traceback

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.error import ConnectionDone, ConnectionLost
from twisted.python import failure, log

from labrad import constants as C, types as T, util
from labrad.decorators import setting
from labrad.wrappers import ClientAsync


class Signal(object):
    """A Signal object is a simple publish/subscribe messaging primitive.

    Servers expose signals as settings that clients or other servers can
    make requests to.  A request allows the client or server to sign up to
    receive messages when this signal is fired.  All the details of managing
    who is listening for these signals is handled here, so the application
    does not need to worry about it.  The application can simply call the
    signal object and the data given will be sent to all connected listeners.
    """
    def __init__(self, ID, name, returns=[]):
        self.ID = ID
        self.name = name
        self.tag = returns
        self.listeners = {}

    def __call__(self, data, contexts=None, tag=None):
        """Fire a message with the given data to all connected listeners.

        If no context is specified, the message will be sent to all listeners.
        Otherwise, the message will be sent only to those listeners signed
        up in the context or contexts specified.
        """
        cxn = self.parent._cxn
        if contexts is None:
            # send this to everyone
            for context, targets in self.listeners.items():
                for target, ID in targets.items():
                    cxn.sendMessage(target, [(ID, data, self.tag)], context)
        else:
            # this little hack allows one to specify contexts
            # as either a single context tuple, or an iterable of
            # multiple context tuples.
            if isinstance(contexts, tuple) and len(contexts) \
               and not isinstance(contexts[0], tuple):
                contexts = [contexts]
            # send only to those in the specified
            # context or list of contexts
            for context in contexts:
                if context not in self.listeners:
                    continue
                for target, ID in self.listeners[context].items():
                    cxn.sendMessage(target, [(ID, data, self.tag)], context)

    def connect(self, context, target, ID):
        """Connect a listener to this signal.

        Connections are made to a given target/message ID, in a particular
        context.  When the signal is fired later, it can be fired to all listeners,
        or only to those listeners signed up in particular contexts.
        """
        cdict = self.listeners.setdefault(context, {})
        tdict = cdict.setdefault(target, ID)

    def disconnect(self, context=None, target=None):
        """Disconnect listeners identified by context and target."""
        # disconnect a particular target in a particular context
        if context is not None and target is not None:
            if context in self.listeners:
                targets = self.listeners[context]
                if target in targets:
                    del targets[target]
                if not len(targets):
                    del self.listeners[context]
        # disconnect a particular target in any context
        elif target is not None:
            for context, targets in self.listeners.items():
                if target in targets:
                    del targets[target]
                if not len(targets) or context[0] == target:
                    del self.listeners[context]
        # disconnect a particular context
        elif context is not None:
            if context in self.listeners:
                del self.listeners[context]
        # disconnect all listeners
        else:
            self.listeners = {}

    # implement the IRequestHandler interface for connect/disconnect
    def handleRequest(self, server, c, data):
        return self._handler.handleRequest(server, c, data)

    def getRegistrationInfo(self):
        return self._handler.getRegistrationInfo()

    @property
    def returns(self):
        return self._handler.returns

    @property
    def _handler(self):
        """Request handler to manage connect/disconnect requests."""
        if hasattr(self, '_handler_func'):
            return self._handler_func
        @setting(self.ID, self.name, ID=['w'], returns=[''])
        def handler(server, c, ID=None):
            if ID is not None:
                self.connect(c.ID, c.source, ID)
            else:
                self.disconnect(c.ID, c.source)
        handler.__doc__ = """Connect to/Disconnect from signal '%s'

        Passing a word ID will cause messages to be sent to setting ID
        when this signal is fired.  Passing nothing will cancel future messages.
        The message data will be of type '%s'.""" % (self.name, self.tag)
        self._handler_func = handler
        return self._handler_func


class Context(object):
    """Serialize requests in a context and handle context expiration.

    One Context object is created for each request context seen by a
    server.  This has a lock so that requests in the context will happen
    in series, and it also stores context data that will be passed
    in to handlers.  In addition, this object keeps track of whether
    the context has expired, so that requests in expired contexts will
    be terminated properly.
    """

    def __init__(self):
        self.lock = defer.DeferredLock()
        self.expired = False

    def acquire(self):
        """Acquire the lock on this context."""
        self.check()
        return self.lock.acquire()

    def check(self):
        """Check to see whether this context has expired."""
        if self.expired:
            raise Exception("Context expired.")

    def release(self):
        """Release the lock on this context."""
        self.lock.release()

    def expire(self):
        """Mark this context as having expired."""
        self.expired = True


class LabradServer(object):
    """A generic LabRAD server."""

    sendTracebacks = True
    prioritizeWrites = False

    def __init__(self):
        self.description, self.notes = util.parseSettingDoc(self.__doc__)

        self.started = False
        self.stopping = False

        self.onStartup = util.DeferredSignal()
        self.onShutdown = util.DeferredSignal()

        self.settings = {}
        self.signals = []
        self.contexts = {}

    # request handling
    @inlineCallbacks
    def request_handler(self, source, context, flat_records):
        """Handle an incoming request.

        If this is a new context, we create a context object and a lock
        to ensure that requests in this context are serialized.  Then,
        we serve the request.
        """
        # create a new context if needed
        c = self.contexts.get(context, None)
        if c is None:
            c = self.contexts[context] = Context()
            yield c.acquire() # make sure we're the first in line
            c.data = yield self.newContext(context)
            yield self.initContext(c.data)
        else:
            yield c.acquire() # wait for previous requests in this context to finish

        if self.prioritizeWrites:
            # yield here so that pending writes will be sent in preference to processing
            # new requests.  This can help in cases where server settings do long-running
            # computations that block, though we are still limited fundamentally by
            # the completely single-threaded way twisted operates
            yield util.wakeupCall(0.0)
        response = []
        try:
            yield self.startRequest(c.data, source)
            for ID, flat_data in flat_records:
                c.check() # make sure this context hasn't expired
                try:
                    setting = self.settings[ID]
                    result = yield setting.handleRequest(self, c.data, flat_data)
                    response.append((ID, result, setting.returns))
                except Exception, e:
                    response.append((ID, self._getTraceback(e)))
                    break
            c.check() # make sure this context hasn't expired
        finally:
            reactor.callLater(0, c.release)
        returnValue(response)

    def _getTraceback(self, e):
        """Turn an exception into a LabRAD error packet.

        We may send a traceback of the error, depending
        on the value of self.sendTracebacks.
        """
        code = getattr(e, 'code', 0)
        if self.sendTracebacks:
            f = failure.Failure()
            tb = f.getTraceback(elideFrameworkCode=True)
            msg = 'Remote %s' % tb
        else:
            msg = e.__class__.__name__ + ': ' + getattr(e, 'msg', str(e))
        msg = '[%s] %s' % (self.name, msg)
        return T.Error(msg, code)

    # registering setting and signal handlers
    def _findSettingHandlers(self):
        """Find all settings defined for this server."""
        # this is an ad-hoc test; we really should check for the IRequestHandler interface
        members = [getattr(self, name) for name in dir(self)]
        handlers = [m for m in members if hasattr(m, 'handleRequest')]
        return sorted(handlers, key=attrgetter('ID'))

    def _checkSettingConflicts(self, s):
        """Check for conflicts in setting name and ID."""
        for other in self.settings.values():
            if s.ID == other.ID or s.name == other.name:
                msg = "Conflicting settings: '%s' (%d), '%s' (%d)" % \
                      (s.name, s.ID, other.name, other.ID)
                raise AssertionError(msg)

    def addSetting(self, setting, packet=None):
        """Add a new setting to the server.

        If a packet is given, the registration call will be added to the
        packet, otherwise a request will be made to the manager, and we
        return a deferred that will fire when the request is done.
        """
        self._checkSettingConflicts(setting)
        self.settings[setting.ID] = setting
        if packet is None:
            packet = self.client.manager
        info = setting.getRegistrationInfo()
        return packet.s__register_setting(info)

    def removeSetting(self, setting, packet=None):
        """Remove a setting from the server.

        If a packet is given, the deregistration call will be added to the
        packet, otherwise a request will be made to the manager, and we
        return a deferred that will fire when the request is done.
        """
        del self.settings[setting.ID]
        if packet is None:
            packet = self.client.manager
        return packet.s__unregister_setting(setting.ID)

    def addSignal(self, signal, packet=None):
        """Add a new signal to the server.

        We add it to the list of signals and also add the
        request handler for signing up to this signal.
        """
        signal.parent = self
        self.signals.append(signal)
        return self.addSetting(signal, packet)

    def removeSignal(self, signal, packet=None):
        """Remove a signal from this server.

        We remove it from the list of signals and also remove
        the request handler for signing up for this signal.
        """
        self.signals.remove(signal)
        return self.removeSetting(signal, packet)

    @inlineCallbacks
    def startup(self, protocol):
        """Start this server using the given protocol connection.

        Identifies this server to the manager, creates an async wrapper for the
        protocol connection, and then runs initialization callbacks for this
        server.

        Args:
            protocol (labrad.protocol.LabradProtocol): A protocol connection
                to the labrad manager, as returned by labrad.protocol.connect.
                This protocol must have been authenticated prior to calling
                startup.

        Returns:
            twisted.internet.defer.Deferred(None): A deferred that will fire
            once startup is complete.
        """
        try:
            name = getattr(self, 'instanceName', self.name)
            yield protocol.loginServer(name, self.description, self.notes)
            self._cxn = protocol
            self.ID = protocol.ID
            protocol.request_handler = self.request_handler
            protocol.onDisconnect().addBoth(self._connection_lost)
            self.client = ClientAsync(protocol)
            yield self.client._init()
            yield self._initServer()
            self.started = True
            self.onStartup.callback(self)
        except Exception as e:
            log.err("connection failed, disconnecting")
            traceback.print_exc()
            self.disconnect(e)
            raise

    # Network events
    # these methods are called by network events from twisted

    @inlineCallbacks
    def _initServer(self):
        """Called after we've authenticated with the LabRAD manager.

        Here we register the settings and signals found on this server
        and set up message handlers for messages coming from the manager.
        """
        log.msg('%s starting...' % self.name)
        # register handlers for settings and signals
        mgr = self.client.manager
        p = mgr.packet()
        for s in self._findSettingHandlers():
            if isinstance(s, Signal):
                self.addSignal(s, p)
            else:
                self.addSetting(s, p)

        yield p.send()

        # do server-specific initialization
        yield self.initServer()
        # make sure we shut down gracefully when reactor quits or a remote message is fired
        self._shutdownID = reactor.addSystemEventTrigger('before', 'shutdown', self._stopServer)
        self._cxn.addListener(self._stopServer, ID=987654321)

        # sign up for notifications from the manager
        yield mgr.subscribe_to_named_message('Server Connect', 55443322, True)
        yield mgr.subscribe_to_named_message('Server Disconnect', 66554433, True)
        self._cxn.addListener(self._serverConnected, source=mgr.ID, ID=55443322, async=False)
        self._cxn.addListener(self._serverDisconnected, source=mgr.ID, ID=66554433, async=False)

        #yield mgr.notify_on_connect.connect(self._serverConnected)
        #yield mgr.notify_on_disconnect.connect(self._serverDisconnected)
        yield mgr.s__notify_on_context_expiration.connect(
                  self._contextExpired, connectargs=(True,))

        # let the rest of the world know we're ready
        yield mgr.s__start_serving()
        log.msg('%s now serving' % self.name)

    @inlineCallbacks
    def _stopServer(self, *ignored):
        self.stopping = True
        try:
            yield self.stopServer()
        except Exception, e:
            self._error = failure.Failure(e)
        finally:
            try:
                self._cxn.disconnect()
            except Exception:
                pass
            # remove the event trigger, so we don't get
            # called again if the reactor shuts down later
            if hasattr(self, '_shutdownID'):
                reactor.removeSystemEventTrigger(self._shutdownID)

    def _connection_lost(self, reason):
        """Called when the network connection to LabRAD is lost.

        This could happen either because there was an error and the
        connection was lost prematurely, or because we requested a shutdown.
        """
        reason = getattr(self, '_error', reason)
        if not self.started:
            self.onStartup.errback(reason)
        else:
            if self.stopping and (reason is None or reason.check(ConnectionDone, ConnectionLost)):
                self.onShutdown.callback()
            else:
                self.onShutdown.errback(reason)

    def disconnect(self, error=None):
        """Disconnect this server from LabRAD.

        This method returns nothing, but you can call onShutdown()
        to get a deferred that will fire when the shutdown is done.
        """
        if error is not None:
            if not isinstance(error, failure.Failure):
                error = failure.Failure(error)
            self._error = error
        self._stopServer()

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

    # Connect/Disconnect notifications
    # these methods should not be overridden
    def _serverConnected(self, c, data):
        """Handle connection messages from the manager."""
        ID, name = data
        self.serverConnected(ID, name)

    def _serverDisconnected(self, c, data):
        """Handle disconnection messages from the manager."""
        ID, name = data
        self.serverDisconnected(ID, name)

    # these methods should be overridden
    def serverConnected(self, ID, name):
        """Called when a new server connects to LabRAD."""

    def serverDisconnected(self, ID, name):
        """Called when a server disconnects from LabRAD."""


    # Context handling
    # these methods should not be overridden
    def _contextExpired(self, c, data):
        """Handle context expiration messages.

        This gets called by the manager either with a single word,
        to expire all contexts with that high word, or with a tuple
        of high word, low word, to expire just that context.
        """
        if isinstance(data, tuple):
            # context tuple specified
            # expire only this context
            for signal in self.signals:
                signal.disconnect(context=data)
            self._expireContext(data)
        else:
            # client ID specified
            # expire all contexts for this ID
            for signal in self.signals:
                signal.disconnect(target=data)
            self._expireID(data)

    def _expireID(self, ID):
        """Expire all contexts with a given ID (high word)."""
        for context in self.contexts.keys():
            if context[0] == ID:
                self._expireContext(context)

    def _expireContext(self, context):
        """Expire a single context."""
        if context in self.contexts:
            c = self.contexts[context]
            del self.contexts[context]
            c.expire()
            self.expireContext(c.data)

    # these methods may be overridden
    def newContext(self, ID):
        """Create a new context object."""
        c = util.ContextDict()
        c.ID = ID
        return c

    def initContext(self, c):
        """Initialize a new context object."""

    def startRequest(self, c, source):
        """Start a request from source in the given context."""
        c.source = source

    def expireContext(self, c):
        """Expire Context.

        Called when the client that created a context disconnects.
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
    onLog = Signal(13131313, 'signal: log', 't*s')

    def log(self, *messages):
        self.onLog((datetime.now(), messages))

