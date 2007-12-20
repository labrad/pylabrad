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

from twisted.application import service, internet
from twisted.internet import defer, protocol, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.error import ConnectionDone
from twisted.python import failure, log
from twisted.python.components import registerAdapter
from twisted.plugin import IPlugin
from zope.interface import Interface, Attribute, implements

from labrad import util, constants as C, types as T, errors
from labrad.decorators import setting
from labrad.protocol import LabradRequestProtocol
from labrad.wrappers import AsyncClientAdapter

class LabradServerProtocol(LabradRequestProtocol):
    """Standard protocol for labrad servers.

    Most of the server-specific customization goes in the factory,
    not this protocol class.
    """
    def __init__(self):
        LabradRequestProtocol.__init__(self)
        self.queues = {}

    def handlePacket(self, source, context, request, records):
        if request > 0: # incoming request
            if self.factory.serving:
                handle = True
                for ID, data in records:
                    if isinstance(data, Exception):
                        handle = False
                        log.msg('Error in incoming request: %s, %s, %s, %s' %\
                                (source, context, request, records))
                if handle:
                    self.enqueue(source, context, request, records)

        elif request < 0: # response to our request
            self._processRequest(source, context, request, records)

        else: # message
            self._processMessage(source, context, records)

    def enqueue(self, source, context, request, records):
        """Enqueue a packet to be served in a given context."""
        if context not in self.queues:
            # create a new queue for contexts we have not yet seen
            q = self.queues[context] = defer.DeferredQueue()
            q.alive = True
            server = self.serveContext(context, q)
            server.addErrback(self._contextFailed, context)
        else:
            q = self.queues[context]
        q.put((source, request, records))

    def _contextFailed(self, failure, context):
        log.err('Unhandled exception while serving context %s.' % (context,))
        log.err(failure)
        del self.queues[context]

    @inlineCallbacks
    def serveContext(self, context, queue):
        """A generator to serve a single context.

        This generator should run forever, taking packets from the
        input queue for this context and serving up the request.
        """
        ctxtData = self.factory.getDefaultCtxtData()
        queue.ctxtData = ctxtData
        while queue.alive:
            source, request, records = yield queue.get()
            if queue.alive:
                try:
                    yield self.serveRequest(source, context, request,
                                            records, ctxtData)
                except:
                    log.err("Unhandled exception while serving request: " \
                            "source: %s, context: %s, request: %s, " \
                            "records: %s, ctxtData: %s" % \
                            (source, context, request, records, ctxtData))
                    log.err()
            else:
                self.expireRequest(source, context, request)
        # now that this queue is dead, we should cancel any pending
        # requests in this context
        for source, request, records in queue.pending:
            self.expireRequest(source, context, request)

    def handleExpiration(self, data):
        #print 'handling expiration:', data
        if isinstance(data, tuple):
            self.expireContext(data)
        else:
            self.expireAllContexts(data)

    def expireContext(self, context):
        #print 'expiring context:', context
        if context in self.queues:
            q = self.queues[context]
            data = q.ctxtData
            q.alive = False
            self.factory.expireContext(data)
            del self.queues[context]

    def expireAllContexts(self, ID):
        #print 'expiring contexts from ID:', ID
        for context in self.queues.keys():
            if context[0] == ID:
                self.expireContext(context)

    def expireRequest(self, source, context, request):
        """Expire a request that was pending."""
        # TODO: determine if anything needs to be sent here

    @inlineCallbacks
    def serveRequest(self, source, context, request, records, ctxtData):
        """A generator to serve a single request.

        We iterate over the records in this packet, passing them on to
        the appropriate handlers.  Each handler is a generator, possibly
        passing back multiple values.  If a handler returns a deferred,
        we wait for it to fire and then send the result back into the
        handler.  The data returned by the handler is collected and sent
        back to the source of the request.
        """
        replies = []
        q = self.queues[context]
        try:
            for ID, data in records:
                # make information about this request accessible in handlers
                ctxtData.ID = context
                ctxtData.source = source
                result, returns = self.factory.callHandler(ID, ctxtData, data)

                # wait for a deferred result to finish
                if isinstance(result, defer.Deferred):
                    result = yield result

                # append result to replies, with hints about return type
                replies.append((ID, result, returns))
        except Exception, e:
            replies.append((ID, self.addTraceback(e)))
        if q.alive:
            try:
                self.sendPacket(source, context, -request, replies)
            except Exception, e:
                # if an error occurs in flattening, send so client doesn't hang
                # TODO: make the message more helpful (indicate server problem)
                self.sendPacket(source, context, -request, (ID, e))
        else:
            self.expireRequest(source, context, request)

    def addTraceback(self, e):
        code = getattr(e, 'code', 0)
        if self.factory.sendTracebacks:
            f = failure.Failure()
            tb = f.getTraceback(elideFrameworkCode=True)
            msg = 'Remote %s' % tb
        else:
            msg = getattr(e, 'msg', str(e))
        msg = '[%s] %s' % (self.factory.name, msg)
        return T.Error(msg, code)

class ILabradServer(Interface):
    pass

class Signal(object):
    def __init__(self, ID, name, tag):
        self.ID = ID
        self.name = name
        self.tag = tag
        self.listeners = {}

    def __call__(self, data):
        # TODO: remove listeners that fail (listeners may return deferreds)
        # TODO: remove listeners when clients disconnect
        # TODO: isolate listeners so that one failure does not kill the rest
        if hasattr(self, 'parent'):
            for target, ID in self.listeners.items():
                #print "signalling %d, %d: %s." % (target, ID, data)
                self.parent.prot.sendPacket(target, (0, 0), 0, (ID, data))

    def connect(self, key):
        # TODO: use weak references here to prevent memory leaks
        target, ID = key
        self.listeners.setdefault(target, ID)

    def disconnect(self, target):
        if target in self.listeners:
            del self.listeners[target]

class LabradServer(protocol.ClientFactory):
    """A generic labrad server."""

    implements(IPlugin, ILabradServer)

    isServer = True
    protocol = LabradServerProtocol
    sendTracebacks = True

    def __init__(self):
        self.defaultCtxtData = util.ContextDict()
        self.settingMap = {}
        self.createSignals()
        self.findAllSettings()
        self.serving = False
        self.initNotifications()
        self.authenticated = False

    def setName(self, name):
        self.name = name

    def getPass(self):
        if getattr(self, 'password', None) is not None:
            pw = self.password
        elif C.PASSWORD is not None:
            pw = C.PASSWORD
        else:
            pw = getpass.getpass('Enter LabRAD password: ')
        self.password = pw
        return pw

    def findAllSettings(self):
        """Finds all setting in this server.

        Looks up all server methods that are decorated as handlers
        and registers them as settings with labrad.
        """
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
        for oldID, (oldName, oldS) in self.settings.items():
            if ID == oldID or name == oldName:
                msg = "Duplicate settings. New: '%s' (%d), Old: '%s' (%d)" % \
                      (name, ID, oldName, oldID)
                raise AssertionError(msg)

    def settingInfo(self, s):
        name, ID = self.settingMap.get(s.name, (s.name, s.ID))
        descr, notes = util.parseSettingDoc(s.__doc__)
        return long(ID), name, descr, s.accepts, s.returns, notes

    @inlineCallbacks
    def clientConnectionMade(self, prot):
        """Called after we've authenticated with the labrad manager.

        After authorization, we do several things:

           1. Register all server settings
           2. Call "initServer" to do more specific initialization
           3. Start the server loop

        If any of these steps fail, the server will disconnect.
        """
        addr = prot.transport.getPeer()
        self.mgr_host, self.mgr_port = addr.host, addr.port
        self.ID = prot.ID
        self.prot = prot
        C.PASSWORD = self.password
        log.msg('%s starting...' % self.name)
        log.msg('connected to %s:%s' % (addr.host, addr.port))
        try:
            # initialize client connection wrapper
            cxn = self.client = AsyncClientAdapter(prot)
            yield cxn.refresh()
            mgr = cxn.manager

            # register settings
            p = mgr.packet()
            for ID, (name, setting) in sorted(self.settings.items()):
                p.s__register_setting(self.settingInfo(setting))
            yield p.send()

            # do server-specific initialization
            yield self.initServer()
            self.serving = True

            # sign up for notifications when servers connect and disconnect
            yield mgr.notify_on_connect.connect(self.serverConnected)
            yield mgr.notify_on_disconnect.connect(self.serverDisconnected)
            yield mgr.notify_on_disconnect.connect(self.pruneSignals)
            yield mgr.s__notify_on_context_expiration.connect(
                      prot.handleExpiration, True)

            # let the rest of the world know we're ready
            yield mgr.s__start_serving()
        except:
            log.err()
            prot.disconnect()
            self.startup.errback()
        else:
            log.msg('%s now serving.' % self.name)
            self.startup.callback()

    def getDefaultCtxtData(self):
        return copy.deepcopy(self.defaultCtxtData)

    def callHandler(self, ID, ctxtData, data):
        """Call a setting handler in context."""
        name, setting = self.settings[ID]
        result = setting.unpack(self, ctxtData, data)
        return result, setting.returns

    def serverConnected(self, (ID, name)):
        """Called when a new server connects to labrad."""

    def serverDisconnected(self, ID):
        """Called when a server disconnects from labrad."""

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

    def expireContext(self, c):
        """Expire Context.

        Called when a client which created a context disconnects.
        Any cleanup operations on the context should be done here.
        """

    def stopFactory(self):
        """Stop Factory.

        Called when the server is stopped.
        """
        return self.stopServer()

    def createSignals(self):
        for methodName in dir(self):
            sig = getattr(self, methodName)
            if isinstance(sig, Signal):
                self.handleSignalSignup(sig)
                sig.parent = self

    def pruneSignals(self, ID):
        # called when a server disconnects so that we stop sending signals
        for methodName in dir(self):
            sig = getattr(self, methodName)
            if isinstance(sig, Signal):
                sig.disconnect(ID)

    def handleSignalSignup(self, sig):
        #print 'server: %s, creating signal: %s' % (self.name, sig.name)
        @setting(sig.ID, sig.name, data=['w'], returns=[''])
        def handler(self, c, data=None):
            if data is None:
                #print "disconnect %d from signal '%s'." % (c.source, sig.name)
                sig.disconnect(c.source)
            else:
                #print "connect %d, %d to signal '%s'." % (c.source, data, sig.name)
                sig.connect((c.source, data))
        setattr(self, '_signal_' + sig.name, handler)

    def clientConnectionLost(self, connector, reason):
        if not self.authenticated:
            C.PASSWORD = None
        if not self.serving:
            self.startup.errback(reason)
        else:
            # check whether connection closed cleanly
            #print 'connection lost:', reason
            if reason.check(ConnectionDone):
                self.shutdown.callback()
            else:
                self.shutdown.errback(reason)

    def clientConnectionFailed(self, connector, reason):
        self.startup.errback(reason)

    def initNotifications(self):
        self.startup = util.DeferredSignal()
        self.shutdown = util.DeferredSignal()

    @setting(11111111)
    def echo(self, c, data):
        """Echo any packet."""
        return data

    @setting(12121212, returns=['s'])
    def debug(self, c, data):
        """Get a __repr__ of the current context."""
        return repr(c)

class labradService(internet.TCPClient):
    def __init__(self, server):
        self._server = server
        internet.TCPClient.__init__(self, server.host, server.port, server)
        self.setName(server.name)

    @property
    def startup(self):
        return self._server.startup

    @property
    def shutdown(self):
        return self._server.shutdown

registerAdapter(labradService, ILabradServer, service.IService)


