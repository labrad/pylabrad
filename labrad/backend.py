"""Backends for labrad connections

Provides a backend connection that underlies the wrapper client object.
"""

import asyncore
import getpass
import hashlib
import socket
import sys
import threading
import Queue

from labrad import constants as C, errors, types as T
from labrad.support import getNodeName

backends = {}

class BaseConnection(object):
    def __init__(self, name):
        self.name = name or 'Python Client (%s)' % getNodeName()
        self.connected = False
        self._next_context = 1

    def connect(self, host, port=C.MANAGER_PORT, timeout=C.TIMEOUT, password=None):
        self.host = host
        self.port = port
        self.ID = self._doConnect(password)
        self._mgr = ClientManager(self)
        self.connected = True

    def context(self):
        context = 0, self._next_context
        self._next_context += 1
        return context

    def disconnect(self):
        if self.connected:
            self._doDisconnect()
            self.connected = False

    def _doConnect(self, password=None):
        """Implemented by subclass"""

    def _doDisconnect(self):
        """Implemented by subclass"""

    def _send(self, target, records, *args, **kw):
        """Implemented by subclass"""

    def _sendMessage(self, target, records, *args, **kw):
        """Implemented by subclass"""

try:
    from twisted.internet import defer, reactor
    
    from labrad.thread import startReactor
    from labrad.wrappers import getConnection

    class TwistedConnection(BaseConnection):
        def _doConnect(self, password):
            startReactor()
            self._cxn = self._call(getConnection, self.host, self.port, self.name, password).wait()
            return self._cxn.ID
            
        def _doDisconnect(self):
            self._call(self._cxn.disconnect).wait()
            
        def _call(self, func, *args, **kw):
            f = Future()
            def wrapped_func():
                d = defer.maybeDeferred(func, *args, **kw)
                d.addCallbacks(lambda result: f.callback(result),
                               lambda failure: f.errback(failure))
            reactor.callFromThread(wrapped_func)
            return f
            
        def _send(self, target, records, *args, **kw):
            return self._call(self._cxn.sendRequest, target, records, *args, **kw)
    
        def _sendMessage(self, target, records, *args, **kw):
            return self._call(self._cxn.sendMessage, target, records, *args, **kw).wait()
    
    backends['twisted'] = TwistedConnection

except ImportError:
    pass


class AsyncoreConnection(BaseConnection):
    def _doConnect(self, password):
        if password is None:
            password = getPassword()
        self.connected = False
        self._clearCache()
        self._writeQueue = Queue.Queue()
        self._map = {}     
        self._cxn = AsyncoreProtocol(self.host, self.port, self._writeQueue, map=self._map)
        self._loop = threading.Thread(target=self._run)
        self._loop.daemon = True
        self._loop.start()
        try:
            self._cxn.awaitConnection()
            self.connected = True
            return self._doLogin(password, self.name)
        except Exception, e:
            self._cxn.disconnect()
            raise
    
    def _run(self):
        asyncore.loop(map=self._map)
    
    def _doDisconnect(self):
        self._cxn.disconnect()
        self._loop.join()

    def _send(self, target, records, context=(0, 0), timeout=None):
        """Send a request to the given target server.

        Returns a deferred that will fire the resulting data packet when
        the request is completed, or will errback if the request times out
        or errors are returned from labrad.  The target server and settings
        may be given either as word IDs or string names.  If necessary,
        any string names will be looked up before the request is sent.
        Lookup results are cached to avoid lookup overhead on subsequent
        requests to the same server or settings.
        """
        target, records = self._lookupNames(target, records)
        resp = self._sendRequestNoLookup(target, records, context, timeout)
        return resp

    def _sendMessage(self, target, records, context=(0, 0)):
        """Send a message to the specified target."""
        target, records = self._lookupNames(target, records)
        self._sendPacket(target, context, records)
        
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
            resp = self._sendRequestNoLookup(C.MANAGER_ID, recs)
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
        
        return (server, records)

    def _clearCache(self):
        """Clear the cache of looked-up server and settings IDs."""
        self._serverCache = {}
        self._settingCache = {}

    def _sendRequestNoLookup(self, target, records, context=(0, 0), timeout=None):
        """Send a request without doing any lookups of server or setting IDs."""
        if not self.connected:
            raise Exception('Not connected.')
        d = Future()
        if timeout is not None:
            raise Exception('Timeouts not supported in asyncore backend')
        self._sendPacket(target, context, records, d)
        return d

    def _sendPacket(self, target, context, records, future=None):
        """Send a raw packet to the specified target."""
        flatrecs = _flattenRecords(records)
        self._writeQueue.put((target, context, flatrecs, future))

    # login protocol
    def _doLogin(self, password, *ident):
        """Implements the LabRAD login protocol."""
        # send login packet
        resp = self._send(C.MANAGER_ID, []).wait()
        challenge = resp[0][1] # get password challenge
    
        # send password response
        m = hashlib.md5()
        m.update(challenge)
        m.update(password)
        try:
            resp = self._send(C.MANAGER_ID, [(0L, m.digest())]).wait()
        except Exception:
            raise errors.LoginFailedError('Incorrect password.')
        self._loginMessage = resp[0][1] # get welcome message
    
        # send identification
        try:
            resp = self._send(C.MANAGER_ID, [(0L, (1L,) + ident)]).wait()
        except:
            raise errors.LoginFailedError('Bad identification.')
        return resp[0][1] # get assigned ID

backends['asyncore'] = AsyncoreConnection


###
# TODO: eliminate code duplication between this and protocol.py

HEADER_TYPE = T.parseTypeTag('(ww)iww')
PACKET_TYPE = T.parseTypeTag('(ww)iws')
RECORD_TYPE = T.parseTypeTag('wss')

def packetStream(packetHandler):
    """A generator that assembles packets.

    Accepts a function packetHandler that will be called with four arguments
    whenever a packet is completed: source, context, request, records.
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
        records = []
        s = T.Buffer(s)
        while len(s):
            ID, tag, data = T.unflatten(s, RECORD_TYPE)
            rec = ID, T.unflatten(data, tag)
            records.append(rec)
        packetHandler(source, context, request, records)

def _flattenPacket(target, context, request, records):
    """Flatten a packet to the specified target."""
    if isinstance(records, str):
        data = records
    else:
        data = ''.join(_flattenRecord(*rec) for rec in records)
    return PACKET_TYPE.__flatten__((context, request, target, data))

def _flattenRecords(records):
    return ''.join(_flattenRecord(*rec) for rec in records)

def _flattenRecord(ID, data, types=[]):
    """Flatten a piece of data into a record with datatype and property."""
    s, t = T.flatten(data, types)
    return RECORD_TYPE.__flatten__((ID, str(t), str(s)))

class AsyncFailure(object):
    def __init__(self, error=None):
        if error is None:
            self.exctype, self.value = sys.exc_info()[:2]
        else:
            self.exctype, self.value = None, error

    def raiseException(self):
        if self.exctype is None:
            raise self.value
        else:
            raise self.exctype, self.value

class Future(object):
    def __init__(self):
        self.e = threading.Event()
        self.done = False
        self.result = None
        self.callbacks = []

    def addCallback(self, f, *args, **kw):
        if self.done:
            self.result = f(self.result, *args, **kw)
        else:
            self.callbacks.append((f, args, kw))
        return self
        
    def callback(self, result):
        self.result = result
        self.e.set()
    
    def errback(self, error=None):
        if not hasattr(error, 'raiseException'):
            error = AsyncFailure(error)
        self.result = error
        self.e.set()
    
    def wait(self):
        if self.done:
            return self.result
        while True:
            self.e.wait(1)
            if self.e.is_set():
                break
        self.done = True
        result = self.result
        if hasattr(result, 'raiseException'):
            # this can be a twisted Failure our
            # own AsyncFailure class, as defined above
            result.raiseException()
        else:
            for f, args, kw in self.callbacks:
                result = f(result, *args, **kw)
            self.result = result
            return result

    def __repr__(self):
        if self.done:
            return '<Future: result=%r>' % (self.result,)
        else:
            return '<Future: pending...>'

class AsyncoreProtocol(asyncore.dispatcher):
    """Receive and send labrad packets."""
    
    def __init__(self, host, port, writeQueue, **kw):
        asyncore.dispatcher.__init__(self, **kw)
        
        self._connectFuture = Future()
        self._disconnectEvent = threading.Event()
        
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connect((host, port))
        
        self.status = 'connecting'
        
        self.writeQueue = writeQueue
        self._nextRequest = 1
        self._reuse = set()
        self.requests = {}
        self.buffer = ''
    
        # create a generator to assemble the packets
        self.packetStream = packetStream(self.packetReceived)
        self.packetStream.next() # start the packet stream
        
    def awaitConnection(self):
        self._connectFuture.wait()
        
    def disconnect(self):
        """Close down our connection to LabRAD."""
        self._disconnectEvent.set()
    
    def handle_connect(self):
        self._connectFuture.callback(None)
        self.status = 'connected'
    
    def handle_error(self):
        if self.status == 'connecting':
            self._connectFuture.errback()
        self.close()
    
    def handle_close(self):
        for d in self.requests.values():
            d.errback(Exception('Connection lost.'))
        self.close()
    
    def handle_write(self):
        if self._disconnectEvent.is_set():
            self.close()
            return
        while True:
            try:
                target, context, flatrecs, future = self.writeQueue.get_nowait()
                if future is None:
                    # message
                    request = 0
                else:
                    # request
                    request = self._startRequest(future)
                data = _flattenPacket(target, context, request, flatrecs)
                self.buffer += data
            except Queue.Empty:
                break
        sent = self.send(self.buffer)
        self.buffer = self.buffer[sent:]

    def _startRequest(self, future):
        """Send a request without doing any lookups of server or setting IDs."""
        if len(self._reuse):
            n = self._reuse.pop()
        else:
            n = self._nextRequest
            self._nextRequest += 1
        self.requests[n] = future
        return n
    
    def handle_read(self):
        data = self.recv(4096)
        self.packetStream.send(data)
    
    def packetReceived(self, source, context, request, records):
        """Process incoming packet."""
        if request < 0:
            self.responseReceived(source, context, request, records)
        elif request > 0:
            self.requestReceived(source, context, request, records)
        else:
            self.messageReceived(source, context, records)
            
    def responseReceived(self, source, context, request, records):
        """Process incoming response."""
        n = -request
        if n in self.requests: # reply has request number negated
            d = self.requests[n]
            del self.requests[n]
            self._reuse.add(n)
            errors = [r[1] for r in records if isinstance(r[1], Exception)]
            if errors:
                # fail on the first error
                d.errback(errors[0])
            else:
                d.callback(records)
        else:
            # probably a response for a request that has already
            # timed out.  If not, something bad has happened.
            print 'Invalid response: %s, %s, %s, %s' % (source, context, request, records)

    def requestReceived(self, source, context, request, records):
        """Process incoming request."""

    def messageReceived(self, source, context, records):
        """Process incoming messages."""


def getPassword():
    """Get a password, either from the environment, or the command line."""
    if C.PASSWORD is not None:
        pw = C.PASSWORD
    else:
        pw = getpass.getpass('Enter LabRAD password: ')
    return pw



###


def connect(host=C.MANAGER_HOST, port=C.MANAGER_PORT, name=None, backend=None, **kw):
    """Create a backend connection to labrad"""
    if backend is None:
        if 'twisted' in backends:
            backend = 'twisted'
        else:
            backend = 'asyncore'
    cxn = backends[backend](name)
    cxn.connect(host, port, **kw)
    return cxn


class ClientManager:
    """Wraps a backend connection to provide a basic synchronous interface to the Manager."""
    def __init__(self, cxn):
        self.ID = C.MANAGER_ID
        self._cxn = cxn

    def _send(self, packet, *args, **kw):
        """Send a request to the manager and wait for the result."""
        return self._cxn._send(self.ID, packet, *args, **kw).wait()

    def _getIDList(self, setting, data=None):
        resp = self._send([(setting, data)])
        names = self._reorderIDList(resp[0][1])
        return names

    def _reorderIDList(self, L):
        return [(name, ID) for ID, name in L]
        
    def getServersList(self):
        """Get a list of connected servers."""
        return self._getIDList(C.SERVERS_LIST)

    def getServerInfo(self, serverID):
        """Get information about a server."""
        packet = [(C.HELP, long(serverID)),
                  (C.SETTINGS_LIST, long(serverID))]
        resp = self._send(packet)
        descr, notes = resp[0][1]
        settings = self._reorderIDList(resp[1][1])
        return (descr, notes, settings)

    def getSettingsList(self, serverID):
        """Get a list of settings for a server."""
        return self._getIDList(C.SETTINGS_LIST, serverID)

    def getSettingInfo(self, serverID, settingID):
        """Get information about a setting."""
        packet = [(C.HELP, (long(serverID), long(settingID)))]
        resp = self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        return (description, accepts, returns, notes)





