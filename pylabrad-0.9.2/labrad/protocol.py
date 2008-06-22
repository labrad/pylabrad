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

from labrad import errors, types as T, util, constants as C
from labrad.interfaces import ILabradProtocol, ILabradClient, IClientAsync

from twisted.internet import reactor, protocol, defer
from twisted.internet.defer import inlineCallbacks
from twisted.internet.error import ConnectionDone
from twisted.python import failure, log
from zope.interface import Interface, implements

import hashlib
import getpass

DEBUG = 0
DEBUG_SEND = 0
DEBUG_RECV = 0

HEADER_TYPE = T.parseTypeTag('(ww)iww')
PACKET_TYPE = T.parseTypeTag('(ww)iws')
RECORD_TYPE = T.parseTypeTag('wss')

def packetStream(packetHandler):
    """A generator that assembles packets.

    This is the version 2 packet protocol for labrad, with request numbers.
    We use the standard library module struct to decode the data.  The
    leading '>' in the format strings indicates big-endian data, 'I'
    is equivalent to U32, and 'B' is equivalent to U8.
    """
    buf = ''
    while True:
        # get packet header (20 bytes)
        while len(buf) < 20:
            buf += yield 0
        hdr, buf = buf[:20], buf[20:]
        context, request, source, length = T.unflatten(hdr, HEADER_TYPE)

        # get packet data
        while len(buf) < length:
            buf += yield 0
        s, buf = buf[:length], buf[length:]

        # unflatten the data
        try:
            records = []
            s = T.Buffer(s)
            while len(s):
                ID, tag, data = T.unflatten(s, RECORD_TYPE)
                rec = ID, T.unflatten(data, tag)
                records.append(rec)
        except:
            # something went wrong in the unflattening
            log.err()
        else:
            # packet complete.  Call the handler
            packetHandler(source, context, request, records)

def _flattenPacket(target, context, request, records):
    """Send a packet to the specified target."""
    data = ''.join(_flattenRecord(*rec) for rec in records)
    return PACKET_TYPE.__flatten__((context, request, target, data))

def _flattenRecord(ID, data, types=[]):
    """Flatten a piece of data into a record with datatype and property."""
    s, t = T.flatten(data, types)
    return RECORD_TYPE.__flatten__((ID, str(t), str(s)))
    
class LabradProtocol(protocol.Protocol):
    """Receive and send labrad packets."""

    implements(ILabradProtocol)
    
    def __init__(self):
        self.authenticated = False
        self._nextRequest = 1
        self._reuse = set()
        self.requests = {}
        self.listeners = {}
    
        # create a generator to assemble the packets
        self.packetStream = packetStream(self.packetReceived)
        self.packetStream.next() # start the packet stream

    # network events
    def connectionMade(self):
        self.factory.clientConnectionMade(self)
        
    def disconnect(self):
        self.transport.loseConnection()
    
    # sending
    def sendPacket(self, target, context, request, records):
        """Send a raw packet to the specified target."""
        raw = _flattenPacket(target, context, request, records)
        self.transport.write(raw)
            
    def sendMessage(self, target, records, context=(0, 0)):
        """Send a message to the specified target."""
        self.sendPacket(target, context, 0, records)

    def sendRequest(self, target, records, context=(0, 0), timeout=None):
        """Send a request to the given target server.

        Returns a deferred that will fire the resulting data packet when
        the request is completed, or will errback if the request times out
        or errors are returned from labrad.
        """
        if len(self._reuse):
            n = self._reuse.pop()
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
        self._reuse.add(n) # reuse request numbers
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
            errors = [rec[1] for rec in records if isinstance(rec[1], Exception)]
            if errors:
                # fail on the first error
                d.errback(errors[0])
            else:
                d.callback(records)
        #else:
        #    # probably a response for a request that has already
        #    # timed out.  If not, something bad has happened.
        #    log.msg('invalid response: %s, %s, %s, %s' % (source, context, request, records))

    def messageReceived(self, source, context, records):
        """Process incoming messages."""
        for ID, data in records:
            listeners = self.listeners.get(ID, []) or \
                        self.listeners.get((source, ID), [])
            for listener, args, kw in listeners:
                listener(data, *args, **kw)

    # message handling
    def addListener(self, key, listener, *args, **kw):
        """Add a listener for messages to the specified key.

        The key should be either a setting ID to handle messages
        from any source to the specified ID, or a tuple of
        (source, setting ID) to handle messages from a single source.
        """
        if DEBUG: print "listening to %s with %s" % (key, listener)
        listeners = self.listeners.setdefault(key, [])
        listeners.append((listener, args, kw))

    def removeListener(self, key, listener):
        self.listeners[key] = [l for l in self.listeners[key] if l[0] != listener]

# factory
class LabradClient(protocol.ClientFactory):
    """A client connection to LabRAD."""
    
    implements(ILabradClient)
    
    protocol = LabradProtocol

    def __init__(self, name=None):
        self.name = name or 'Python Client (%s)' % util.getNodeName()
        self.started = False
        self.onStartup = util.DeferredSignal()
        self.onShutdown = util.DeferredSignal()

    def getPassword(self):
        if getattr(self, 'password', None) is not None:
            pw = self.password
        elif C.PASSWORD is not None:
            pw = C.PASSWORD
        else:
            pw = getpass.getpass('Enter LabRAD password: ')
        return pw

    def getIdentification(self):
        return (self.name,)
    
    # login/authentication protocol
    @inlineCallbacks
    def clientConnectionMade(self, protocol):
        """Implements the LabRAD login protocol."""
        try:
            # send login packet
            resp = yield protocol.sendRequest(C.MANAGER_ID, [])
            challenge = resp[0][1] # get password challenge

            # send password response
            password = self.getPassword()
            m = hashlib.md5()
            m.update(challenge)
            m.update(password)
            try:
                # hack to get an error message to show up for incorrect password
                self._error = errors.LoginFailedError('Incorrect password.')
                resp = yield protocol.sendRequest(C.MANAGER_ID, [(0L, m.digest())])
                del self._error
            except:
                self.password = C.PASSWORD = None
                raise
            message = resp[0][1] # get welcome message
            self.password = C.PASSWORD = password

            # send identification
            ident = (1L,) + tuple(self.getIdentification())
            self._error = errors.LoginFailedError('Server name already in use.')
            resp = yield protocol.sendRequest(C.MANAGER_ID, [(0L, ident)])
            del self._error
            self.ID = resp[0][1] # get assigned ID
            
            addr = protocol.transport.getPeer()
            self.mgr_host, self.mgr_port = addr.host, addr.port
            self._cxn = protocol
            self.client = IClientAsync(protocol)
            yield self.client.refresh()
            yield self.loginSucceeded(message)
            self.started = True
            self.onStartup.callback(self)
        except Exception, e:
            self.disconnect(e)
    
    def loginSucceeded(self, message):
        """Called by the protocol when we have successfully logged in."""
    
    def disconnect(self, error=None):
        if error:
            self._error = failure.Failure(error)
        self._cxn.disconnect()
    
    def clientConnectionFailed(self, connector, reason):
        self.onStartup.errback(reason)
        
    def clientConnectionLost(self, connector, reason):
        reason = getattr(self, '_error', reason)
        if not self.started:
            self.onStartup.errback(reason)
        else:
            if reason.check(ConnectionDone):
                self.onShutdown.callback()
            else:
                self.onShutdown.errback(reason)
