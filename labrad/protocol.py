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
labrad.protocol

Defines the sending and receiving of packets on the network,
as well as the protocol for connecting to the Manager and
authenticating.
"""

import hashlib

from twisted.internet import reactor, protocol, defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import failure, log
from zope.interface import implements

from labrad import constants as C, errors, util
from labrad.interfaces import ILabradProtocol, IMessageContext
from labrad.stream import packetStream, flattenPacket

    
class LabradProtocol(protocol.Protocol):
    """Receive and send labrad packets."""

    implements(ILabradProtocol)
    
    def __init__(self):
        self.disconnected = False
        self._nextRequest = 1
        self.pool = set()
        self.requests = {}
        self.listeners = {}
        self._messageLock = defer.DeferredLock()
        self.clearCache()
    
        # create a generator to assemble the packets
        self.packetStream = packetStream(self.packetReceived)
        self.packetStream.next() # start the packet stream
        
        self.onDisconnect = util.DeferredSignal()

    # network events
    def connectionMade(self):
        # set the SO_KEEPALIVE option on all connections
        self.transport.setTcpNoDelay(True)
        self.transport.setTcpKeepAlive(True)
    
    def connectionLost(self, reason):
        """Called when the network connection is lost.
        
        This can be due to the disconnect() method being
        called, or because of some network error.
        """
        self.disconnected = True
        for d in self.requests.values():
            d.errback(Exception('Connection lost.'))
        if reason == protocol.connectionDone:
            self.onDisconnect.callback(None)
        else:
            self.onDisconnect.errback(reason)
        
    def disconnect(self):
        """Close down the connection to LabRAD."""
        self.disconnected = True
        self.transport.loseConnection()
    
    # sending
    def sendPacket(self, target, context, request, records):
        """Send a raw packet to the specified target."""
        raw = flattenPacket(target, context, request, records)
        self.transport.write(raw)
    
    @inlineCallbacks        
    def sendMessage(self, target, records, context=(0, 0)):
        """Send a message to the specified target."""
        target, records = yield self._lookupNames(target, records)
        self.sendPacket(target, context, 0, records)

    @inlineCallbacks
    def sendRequest(self, target, records, context=(0, 0), timeout=None):
        """Send a request to the given target server.

        Returns a deferred that will fire the resulting data packet when
        the request is completed, or will errback if the request times out
        or errors are returned from labrad.  The target server and settings
        may be given either as word IDs or string names.  If necessary,
        any string names will be looked up before the request is sent.
        Lookup results are cached to avoid lookup overhead on subsequent
        requests to the same server or settings.
        """
        target, records = yield self._lookupNames(target, records)
        resp = yield self._sendRequestNoLookup(target, records, context, timeout)
        returnValue(resp)
            
    @inlineCallbacks
    def _lookupNames(self, server, records):
        """Translate server and setting names into IDs.

        We first attempt to look up these names in the local cache.
        If any are not found there, we fire off a request to the
        Manager to lookup the necessary IDs, and then cache the
        result.
        """
        records = list(records)
        
        # try to lookup server in cache
        if isinstance(server, str) and server in self._serverCache:
            server = self._serverCache[server]
            
        # try to lookup settings in cache
        if server in self._settingCache:
            settings = self._settingCache[server]
            for i, rec in enumerate(records):
                name = rec[0]
                if isinstance(name, str) and name in settings:
                    records[i] = (settings[name],) + tuple(rec[1:]) 
        
        # check to see whether there is still anything to look up
        settingLookups = [(i, rec[0]) for i, rec in enumerate(records)
                                      if isinstance(rec[0], str)]
        if isinstance(server, str) or len(settingLookups):
            # need to do additional lookup here
            if len(settingLookups):
                indices, names = zip(*settingLookups)
            else:
                indices, names = [], []
            # send the actual lookup request
            recs = [(C.LOOKUP, (server, names), ['w*s', 's*s'])]
            resp = yield self._sendRequestNoLookup(C.MANAGER_ID, recs)
            serverID, IDs = resp[0][1]
            # cache the results
            if isinstance(server, str):
                self._serverCache[server] = serverID
            server = serverID
            settings = self._settingCache.setdefault(server, {})
            settings.update(zip(names, IDs))
            # update the records for the packet
            for index, ID in zip(indices, IDs):
                records[index] = (ID,) + tuple(records[index][1:])

        returnValue((server, records))

    def clearCache(self):
        """Clear the cache of looked-up server and settings IDs."""
        self._serverCache = {}
        self._settingCache = {}

    def _sendRequestNoLookup(self, target, records, context=(0, 0), timeout=None):
        """Send a request without doing any lookups of server or setting IDs."""
        if self.disconnected:
            raise Exception('Already disconnected.')
        if len(self.pool):
            n = self.pool.pop()
        else:
            n = self._nextRequest
            self._nextRequest += 1

        self.requests[n] = d = defer.Deferred()
        if timeout is not None:
            timeoutCall = reactor.callLater(timeout, d.errback,
                                            errors.RequestTimeoutError())
            d.addBoth(self._cancelTimeout, timeoutCall)
        d.addBoth(self._finishRequest, n)
        self.sendPacket(target, context, n, records)
        return d
        
    def _cancelTimeout(self, result, timeoutCall):
        """Cancel a pending request timeout call."""
        if timeoutCall.active():
            timeoutCall.cancel()
        return result
        
    def _finishRequest(self, result, n):
        """Finish a request."""
        del self.requests[n]
        self.pool.add(n) # reuse request numbers
        return result
    
    # receiving
    def dataReceived(self, data):
        self.packetStream.send(data)
    
    def packetReceived(self, source, context, request, records):
        """Process incoming packet."""
        if request > 0:
            self.requestReceived(source, context, request, records)
        elif request < 0:
            self.responseReceived(source, context, request, records)
        else:
            self.messageReceived(source, context, records)
        
    def requestReceived(self, source, context, request, records):
        """Process incoming request."""
            
    def responseReceived(self, source, context, request, records):
        """Process incoming response."""
        if -request in self.requests: # reply has request number negated
            d = self.requests[-request]
            errors = [r[1] for r in records if isinstance(r[1], Exception)]
            if errors:
                # fail on the first error
                d.errback(errors[0])
            else:
                d.callback(records)
        else:
            # probably a response for a request that has already
            # timed out.  If not, something bad has happened.
            log.msg('Invalid response: %s, %s, %s, %s' % \
                    (source, context, request, records))

    def messageReceived(self, source, context, records):
        """Process incoming messages."""
        self._messageLock.run(self._dispatchMessage, source, context, records)
        
    @inlineCallbacks
    def _dispatchMessage(self, source, context, records):
        """Dispatch a message to all matching listeners."""
        for ID, data in records:
            msgCtx = MessageContext(source, context, ID)
            keys = ((s, c, i) for s in (source, None)
                              for c in (context, None)
                              for i in (ID, None)
                              if (s, c, i) in self.listeners)
            for key in keys:
                for listener, async in self.listeners[key]:
                    func, args, kw = listener
                    try:
                        d = func(msgCtx, data, *args, **kw)
                        if not isinstance(d, defer.Deferred):
                            continue
                        if async:
                            d.addErrback(self._handleListenerError,
                                         msgCtx, data, listener)
                        else:
                            yield d
                    except Exception:
                        self._handleListenerError(
                            failure.Failure(), msgCtx, data, listener)
                        
    def _handleListenerError(self, failure, msgCtx, data, listener):
        """Catch errors in message listeners.
        
        Just prints out a (hopefully informative) message
        about any errors that may have occurred.
        """
        print 'Unhandled error in message listener:', msgCtx, data, listener
        failure.printTraceback(elideFrameworkCode=1)
                        
    # message handling
    def addListener(self, listener, source=None, context=None, ID=None, async=True, args=(), kw={}):
        """Add a listener for messages with the specified attributes.

        When a message with the specified source, context and ID is received,
        listener will be called with the message data, along with the args and
        keyword args specified here.  async determines how message listeners
        that return deferreds are to be handled.  If async is True, the message
        dispatcher will not wait for the deferred returned by a listener to fire.
        However, if async is False, the dispatcher will wait for this deferred
        before firing any more messages.
        """
        key = (source, context, ID)
        listeners = self.listeners.setdefault(key, [])
        listeners.append(((listener, args, kw), async))

    def removeListener(self, listener, source=None, context=None, ID=None):
        """Remove a listener for messages."""
        key = (source, context, ID)
        listeners = [l for l in self.listeners[key] if l[0][0] != listener]
        if len(listeners):
            self.listeners[key] = listeners
        else:
            del self.listeners[key]

    # login protocol
    def loginClient(self, password, name):
        """Log in as a client."""
        return self._doLogin(password, name)
    
    def loginServer(self, password, name, descr, notes):
        """Log in as a server."""
        return self._doLogin(password, name, descr, notes)

    @inlineCallbacks
    def _doLogin(self, password, *ident):
        """Implements the LabRAD login protocol."""
        # send login packet
        resp = yield self.sendRequest(C.MANAGER_ID, [])
        challenge = resp[0][1] # get password challenge
    
        # send password response
        m = hashlib.md5()
        m.update(challenge)
        m.update(password)
        try:
            resp = yield self.sendRequest(C.MANAGER_ID, [(0L, m.digest())])
        except Exception:
            raise errors.LoginFailedError('Incorrect password.')
        self.password = C.PASSWORD = password # save password, since it worked
        self.loginMessage = resp[0][1] # get welcome message
    
        # send identification
        try:
            resp = yield self.sendRequest(C.MANAGER_ID, [(0L, (1L,) + ident)])
        except Exception:
            raise errors.LoginFailedError('Bad identification.')
        self.ID = resp[0][1] # get assigned ID


class MessageContext(object):
    """Object to be passed as the first argument to message handlers."""
    
    implements(IMessageContext)
    
    def __init__(self, source, context, target):
        self.source = source
        self.ID = context
        self.target = target
        
    def __repr__(self):
        return 'MessageContext(source=%s, ID=%s, target=%s)' % (self.source, self.ID, self.target)

# factory for churning out LabRAD connections
factory = protocol.ClientCreator(reactor, LabradProtocol)
