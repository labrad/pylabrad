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
from twisted.internet import reactor, protocol, defer
from twisted.python import log
from zope.interface import Interface, implements

import hashlib
import getpass
from datetime import datetime

DEBUG = 0
DEBUG_SEND = 0
DEBUG_RECV = 0

def _assemble(packetHandler):
    """A generator that assembles packets.

    This is the version 2 packet protocol for labrad, with request numbers.
    We use the standard library module struct to decode the data.  The
    leading '>' in the format strings indicates big-endian data, 'I'
    is equivalent to U32, and 'B' is equivalent to U8.
    """
    buf = ''

    while True:
        # the packet header is 20 bytes
        while len(buf) < 20: buf += yield 0
        hdr, buf = buf[:20], buf[20:]
        context, request, source, datalen = T.unflatten(hdr, '(ww)iww')
        if DEBUG_RECV:
            print 'got header:', context, request, source, datalen

        # read in enough the data
        while len(buf) < datalen: buf += yield 0
        s, buf = buf[:datalen], buf[datalen:]

        if DEBUG_RECV:
            print 'got packet:'
            print util.dump(hdr + s)

        # unflatten the data
        try:
            records = []
            s = T.Buffer(s)
            while len(s):
                # TODO: error checking: strings must be fully consumed
                ID, tag, data = T.unflatten(s, 'wss')
                #if DEBUG_RECV: print 'record:', ID, repr(tag), repr(data)
                rec = ID, T.unflatten(data, tag)
                #if DEBUG_RECV: print 'after unflattening:', rec
                records.append(rec)
        except:
            # something went wrong in the unflattening
            if DEBUG_RECV: print 'Received corrupt data:\n%s' % util.dump(raw)
            log.err()
        else:
            # packet complete.  Call the appropriate handler
            packetHandler(source, context, request, records)

def _flattenPacket(target, context, request, records):
    """Send a packet to the specified target."""
    records = records if isinstance(records, list) else [records]
    data = ''.join(_flattenRecord(*rec) for rec in records)
    return T.flatten((context, request, target, data), '(ww)iws')[0]

def _flattenRecord(ID, data, types=[]):
    """Flatten a piece of data into a record with datatype and property."""
    s, t = T.flatten(data, types)
    return T.flatten((long(ID), str(t), str(s)), 'wss')[0]

class LabradProtocol(protocol.Protocol):
    """Receive and send labrad packets."""

    def __init__(self):
        # create a generator to assemble the packets
        self.assembler = _assemble(self.packetReceived)
        self.assembler.next() # start the generator loop
        self.authenticator = self.authenticate()
        self.authenticator.next() # start the authentication loop
        self.authenticated = False

    def connectionMade(self):
        self.timeoutCall = reactor.callLater(C.TIMEOUT, self.timeout)
        if DEBUG: print 'made a connection.  sending login packet.'
        self.sendPacket(C.MANAGER_ID, (1, 0), 1, [])

    def connectionLost(self, reason):
        if not self.authenticated:
            print 'could not authenticate.'

    def dataReceived(self, data):
        self.assembler.send(data)

    def authenticate(self):
        # first packet contains password hash
        source, context, request, records = yield 0
        challenge = records[0][1]

        # send password response
        m = hashlib.md5()
        m.update(challenge)
        m.update(self.factory.getPass())
        self.sendPacket(C.MANAGER_ID, (1, 0), 1, (0, m.digest()))

        # second packet contains welcome message
        source, context, request, records = yield 0
        msg = records[0][1]
        if isinstance(msg, Exception):
            print msg
            self.disconnect() # unable to log in for some reason
            return
        if DEBUG: print msg # welcome message from labrad

        # send identification
        if self.factory.isServer:
            d = 1L, self.factory.name, self.factory.__doc__ or '', ''
        else:
            d = 1L, self.factory.name
        self.sendPacket(C.MANAGER_ID, (1, 0), 1, (0, d))

        # third packet contains our ID
        source, context, request, records = yield 0
        ID = records[0][1]
        if isinstance(ID, Exception):
            print ID
            self.disconnect()
            return
        self.ID = records[0][1]
        self.timeoutCall.cancel()
        self.authenticated = True
        self.factory.authenticated = True
        self.factory.clientConnectionMade(self)
        yield 1

    def packetReceived(self, source, context, request, records):
        """Called whenever a complete packet is received."""
        if DEBUG_RECV:
            print 'packetReceived:', source, context, request, records
        if not self.authenticated:
            self.authenticator.send((source, context, request, records))
        else:
            self.handlePacket(source, context, request, records)

    def handlePacket(self, source, context, request, records):
        """Called when we get a packet that needs to be handled."""

    def sendPacket(self, target, context, request, records):
        """Send a packet to the specified target."""
        raw = _flattenPacket(target, context, request, records)
        if DEBUG_SEND:
            print 'sending:'
            print util.dump(raw)
        self.transport.write(raw)

    def disconnect(self):
        self.transport.loseConnection()

    def timeout(self):
        self.transport.loseConnection()

class ILabradRequestProtocol(Interface):
    pass

class LabradRequestProtocol(LabradProtocol):
    """Wrap up packets in deferreds to handle request numbering."""

    implements(ILabradRequestProtocol)

    def __init__(self):
        LabradProtocol.__init__(self)
        self._nextRequest = 1
        self._reuse = set()
        self.requests = {}
        self.listeners = {}

    def request(self, target, records, context=(0, 0), timeout=None):
        """Send a request to the given target server.

        Returns a deferred that will fire the resulting data packets when
        the request is completed, or will errback if the request times out
        or errors are returned from labrad.
        """
        if len(self._reuse):
            req_num = self._reuse.pop()
        else:
            req_num = self._nextRequest
            self._nextRequest += 1

        req = LabradRequest(timeout)
        req.deferred.addBoth(self._finishRequest, req_num)
        self.requests[req_num] = req
        self.sendPacket(target, context, req_num, records)
        return req.deferred

    def _finishRequest(self, result, req_num):
        """Finish a request."""
        del self.requests[req_num]
        self._reuse.add(req_num) # this request number can be reused
        return result

    def handlePacket(self, source, context, request, records):
        if request:
            self._processRequest(source, context, request, records)
        else:
            self._processMessage(source, context, records)

    def _processRequest(self, source, context, request, records):
        """Process incoming packets associated with a request."""
        if -request in self.requests: # replies will have req num negated
            req = self.requests[-request]
            req.handleData(records)
        else:
            print 'invalid request:', source, context, request, records

    def _processMessage(self, source, context, records):
        """Process incoming messages."""
        for ID, data in records:
            listeners = self.listeners.get(ID, []) or \
                        self.listeners.get((source, ID), [])
            for listener in listeners:
                listener(data)

    def addListener(self, key, listener):
        """Add a listener for messages to the specified key.

        The key should be either a setting ID to handle messages
        from any source to the specified ID, or a tuple of
        (source, setting ID) to handle messages from a single source.
        """
        if DEBUG: print "listening to %s with %s" % (key, listener)
        listeners = self.listeners.setdefault(key, [])
        listeners.append(listener)

    def removeListener(self, key, listener):
        self.listeners[key].remove(listener)

class LabradRequest:
    """Handle packets coming back from a particular request."""

    def __init__(self, timeout=None):
        self.deferred = defer.Deferred()
        if timeout:
            self.timeoutCall = reactor.callLater(timeout, self._timeout)

    def _timeout(self):
        self.deferred.errback(errors.RequestTimeoutError())

    def handleData(self, records):
        if DEBUG:
            print 'request done:', records
        if hasattr(self, 'timeoutCall'):
            self.timeoutCall.cancel()
        errors = [rec[1] for rec in records if isinstance(rec[1], Exception)]
        if errors:
            # fail on the first error
            self.deferred.errback(errors[0])
        else:
            self.deferred.callback(records)

# factory
class LabradClientFactory(protocol.ClientFactory):

    isServer = False
    protocol = LabradRequestProtocol

    def __init__(self, name=None, timeout=C.TIMEOUT):
        self.name = name or 'python client (%s)' % util.getNodeName()
        self.timeout = timeout
        self.authenticated = False
        self._reset()

    def getPass(self):
        if getattr(self, 'password', None) is not None:
            pw = self.password
        elif C.PASSWORD is not None:
            pw = C.PASSWORD
        else:
            pw = getpass.getpass('Enter LabRAD password: ')
        self.password = pw
        return pw

    def _reset(self):
        self.connectionRequests = []
        self.disconnectWaiters = []
        self._cxn = None

    def clientConnectionMade(self, protocol):
        self._cxn = protocol
        C.PASSWORD = self.password
        ds = self.connectionRequests
        self.connectionRequests = []
        for d in ds:
            d.callback(self._cxn)

    def getConnection(self):
        if self._cxn:
            return defer.succeed(self._cxn)
        d = defer.Deferred()
        self.connectionRequests.append(d)
        return d

    def notifyOnDisconnect(self):
        d = defer.Deferred()
        self.disconnectWaiters.append(d)
        return d

    def _failAll(self, reason):
        ds = self.connectionRequests
        self._reset()
        for d in ds:
            d.errback(reason)

    def _connectionLost(self, reason):
        ds = self.disconnectWaiters
        self._reset()
        for d in ds:
            d.errback(reason)

    def clientConnectionLost(self, connector, reason):
        if not self.authenticated:
            C.PASSWORD = None
            self._failAll(reason)
        else:
            self._connectionLost(reason)


    def clientConnectionFailed(self, connector, reason):
        self._failAll(reason)



