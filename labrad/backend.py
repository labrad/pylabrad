"""Backends for labrad connections

Provides a backend connection that underlies the wrapper client object.
"""

from __future__ import absolute_import

import asyncore
import hashlib
import socket
import threading
import Queue

from concurrent.futures import Future

from labrad import constants as C, support, types as T
from labrad.errors import LoginFailedError
from labrad.stream import packetStream, flattenPacket, flattenRecords

backends = {}

class BaseConnection(object):
    def __init__(self, name=None):
        self.name = name or 'Python Client ({})'.format(support.getNodeName())
        self._connected = threading.Event()
        self._nextContext = 1

    def context(self):
        """Create a new context for use with this connection"""
        ctx = 0, self._nextContext
        self._nextContext += 1
        return ctx

    def connect(self, host=C.MANAGER_HOST, port=None, timeout=C.TIMEOUT,
                password=None, tls_mode=C.MANAGER_TLS):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls_mode = tls_mode
        self.password = password
        self.ID = self._connect(password, timeout, tls_mode=tls_mode)

    @property
    def connected(self):
        return self._connected.is_set()

    def disconnect(self):
        if self.connected:
            self._disconnect()

    def spawn(self):
        """Start a new independent backend connection to the same manager."""
        cls = self.__class__
        inst = cls(name=self.name)
        inst.connect(host=self.host, port=self.port, timeout=self.timeout,
                     password=self.password, tls_mode=self.tls_mode)
        return inst

    def _connect(self, password=None, timeout=None, tls_mode=C.MANAGER_TLS):
        """Implemented by subclass"""

    def _disconnect(self):
        """Implemented by subclass"""

    def sendRequest(self, target, records, *args, **kw):
        """Implemented by subclass"""

    def sendMessage(self, target, records, *args, **kw):
        """Implemented by subclass"""


try:
    from twisted.internet import defer, reactor

    from labrad.thread import startReactor
    from labrad.wrappers import getConnection

    class TwistedConnection(BaseConnection):
        def _connect(self, password, _timeout, tls_mode):
            @defer.inlineCallbacks
            def _connect_deferred():
                cxn = yield getConnection(self.host, self.port, self.name,
                                          password, tls_mode=tls_mode)
                self._connected.set()

                # Setup a coroutine that will clear the connected flag when the
                # connection is lost. We launch this but do not yield to wait
                # for the result because we want this to happen asynchronously
                # in the background.
                @defer.inlineCallbacks
                def handle_disconnect():
                    try:
                        yield cxn.onDisconnect()
                    except Exception:
                        pass
                    self._connected.clear()
                handle_disconnect()

                defer.returnValue(cxn)
            startReactor()
            self.cxn = self.call(_connect_deferred).result()
            return self.cxn.ID

        def _disconnect(self):
            self.call(self.cxn.disconnect).result()

        def call(self, func, *args, **kw):
            """Run func in the twisted reactor; return result as a future."""
            f = Future()
            @defer.inlineCallbacks
            def wrapped():
                try:
                    result = yield defer.maybeDeferred(func, *args, **kw)
                    f.set_result(result)
                except Exception as e:
                    f.set_exception(e)
            reactor.callFromThread(wrapped)
            return f

        def sendRequest(self, target, records, *args, **kw):
            return self.call(self.cxn.sendRequest, target, records, *args, **kw)

        def sendMessage(self, target, records, *args, **kw):
            return self.call(self.cxn.sendMessage, target, records, *args, **kw).result()

    backends['twisted'] = TwistedConnection

except ImportError:
    pass


class AsyncoreConnection(BaseConnection):
    def _connect(self, password, timeout, tls_mode):
        tls_mode = C.check_tls_mode(tls_mode)
        if tls_mode == 'on':
            raise Exception('TLS is not currently supported with the asyncore '
                            'backend')
        self.serverCache = {}
        self.settingCache = {}
        if self.port is None:
            port = C.MANAGER_PORT_TLS if tls_mode == 'on' else C.MANAGER_PORT
        else:
            port = self.port
        try:
            sock = socket.create_connection((self.host, port),
                                            timeout or 5)
            socketMap = {}
            self.cxn = AsyncoreProtocol(sock,
                                        connected=self._connected,
                                        map=socketMap)
            self.loop = threading.Thread(target=asyncore.loop,
                kwargs={'timeout':0.01, 'map': socketMap})
            self.loop.daemon = True
            self.loop.start()
            try:
                ID = self.login(password, self.name)
                self._connected.set()
                return ID
            except Exception, e:
                self.disconnect()
                raise
        except LoginFailedError:
            raise
        except Exception, e:
            raise LoginFailedError(e)

    def _disconnect(self):
        self.cxn.drop()
        self.loop.join()

    def login(self, password, *ident):
        # send login packet
        resp = self.sendRequest(C.MANAGER_ID, []).result()
        challenge = resp[0][1] # get password challenge

        # send password response
        if password is None:
            password = support.get_password(self.host, self.port)
        m = hashlib.md5()
        m.update(challenge)
        m.update(password)
        try:
            resp = self.sendRequest(C.MANAGER_ID, [(0L, m.digest())]).result()
        except Exception:
            raise LoginFailedError('Incorrect password.')
        support.cache_password(self.host, self.port, password)
        self.password = password
        self.loginMessage = resp[0][1] # get welcome message

        # send identification
        try:
            resp = self.sendRequest(C.MANAGER_ID, [(0L, (1L,) + ident)]).result()
        except Exception:
            raise LoginFailedError('Bad identification.')
        return resp[0][1] # get assigned ID

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
        target, records = self._lookupNames(target, records)
        return self._sendRequestNoLookup(target, records, context, timeout)

    def sendMessage(self, target, records, context=(0, 0)):
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
        if isinstance(server, str) and server in self.serverCache:
            server = self.serverCache[server]

        # try to lookup settings in cache
        if server in self.settingCache:
            settings = self.settingCache[server]
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
                self.serverCache[server] = serverID
            server = serverID
            settings = self.settingCache.setdefault(server, {})
            settings.update(zip(names, IDs))
            # update the records for the packet
            for index, ID in zip(indices, IDs):
                records[index] = (ID,) + tuple(records[index][1:])

        return (server, records)

    def _sendRequestNoLookup(self, target, records, context=(0, 0), timeout=None):
        """Send a request without doing any lookups of server or setting IDs."""
        d = Future()
        if timeout is not None:
            raise Exception('Timeouts not supported in asyncore backend')
        self._sendPacket(target, context, records, d)
        return d

    def _sendPacket(self, target, context, records, future=None):
        """Send a raw packet to the specified target."""
        flatrecs = flattenRecords(records)
        try:
            self.cxn.enqueue(target, context, flatrecs, future)
        except Exception:
            self.connected = False
            raise


backends['asyncore'] = AsyncoreConnection

class AsyncoreProtocol(asyncore.dispatcher):
    """Receive and send labrad packets."""

    def __init__(self, socket, connected, **kw):
        asyncore.dispatcher.__init__(self, socket, **kw)

        self.connected = connected
        self.alive = True
        self.lock = threading.Lock()
        self.nextRequest = 1
        self.requests = {}
        self.pool = set()
        self.queue = Queue.Queue()
        self.buffer = ''

        # create a generator to assemble the packets
        self.stream = packetStream(self.handleResponse)
        self.stream.next() # start the packet stream

    def enqueue(self, target, context, flatrecs, future):
        """Called from another thread to enqueue a packet"""
        with self.lock:
            if not self.alive:
                raise Exception('not connected')
            self.queue.put((target, context, flatrecs, future))

    def drop(self):
        self.queue.put(None)

    def handle_error(self):
        self.terminate(Exception('AsyncoreProtocol error'))

    def handle_close(self):
        self.terminate(Exception('Connection lost'))

    def terminate(self, reason):
        with self.lock:
            self.alive = False
        self.connected.clear()
        try:
            self.close()
        finally:
            self.flushCommands()
            for d in self.requests.values():
                d.set_exception(reason)

    def readable(self):
        return True

    def writable(self):
        """Only register for writing if we have something to write

        For some reason each command submitted from the interactive shell
        seems to fire the writing code twice. This isn't really a problem
        because an empty self.queue is properly handeled.
        """
        return not self.queue.empty()

    def handle_write(self):
        if self.flushCommands():
            sent = self.send(self.buffer)
            self.buffer = self.buffer[sent:]

    def flushCommands(self):
        while True:
            try:
                command = self.queue.get_nowait()
            except Queue.Empty:
                break
            if command is None:
                self.terminate('Connection closed')
                return False
            elif isinstance(command, str):
                # Hack to let us write raw data
                # to test error handling
                self.buffer += command
                continue
            target, context, flatrecs, future = command
            if future is None: # message
                request = 0
            else: # request
                request = self.startRequest(future)
            data = flattenPacket(target, context, request, flatrecs)
            self.buffer += data
        return True

    def startRequest(self, future):
        if len(self.pool):
            n = self.pool.pop()
        else:
            n = self.nextRequest
            self.nextRequest += 1
        self.requests[n] = future
        return n

    def handle_read(self):
        data = self.recv(4096)
        self.stream.send(data)

    def handleResponse(self, _source, _context, request, flat_records):
        n = -request # reply has request number negated
        if n not in self.requests:
            # probably a response for a request that has already
            # timed out.  If a message or incoming request, we
            # simply ignore it, since these shouldn't happen.
            return
        future = self.requests[n]
        del self.requests[n]
        self.pool.add(n)
        records = [(ID, flat_data.unflatten()) for ID, flat_data in flat_records]
        errors = [r[1] for r in records if isinstance(r[1], Exception)]
        if errors:
            # fail on the first error
            future.set_exception(errors[0])
        else:
            future.set_result(records)


def connect(host=C.MANAGER_HOST, port=None, name=None, backend=None, **kw):
    """Create a backend connection to labrad"""
    if backend is None:
        if 'twisted' in backends:
            backend = 'twisted'
        else:
            backend = 'asyncore'
    cxn = backends[backend](name)
    cxn.connect(host, port, **kw)
    return cxn


class ManagerService:
    """Wraps a backend connection to provide a basic synchronous interface to the Manager."""
    def __init__(self, cxn):
        self.cxn = cxn

    def getServersList(self):
        """Get list of connected servers."""
        return self._getIDList(T.flatten(C.SERVERS_LIST, 'w'))

    def getServerInfo(self, serverID):
        """Get information about a server."""
        packet = [(C.HELP, T.flatten(serverID, 'w')),
                  (C.SETTINGS_LIST, T.flatten(serverID, 'w'))]
        resp = self._send(packet)
        descr, notes = resp[0][1]
        settings = self._reorderIDList(resp[1][1])
        return (descr, notes, settings)

    def getSettingsList(self, serverID):
        """Get list of settings for a server."""
        return self._getIDList(C.SETTINGS_LIST, T.flatten(serverID, 'w'))

    def getSettingInfo(self, serverID, settingID):
        """Get information about a setting."""
        packet = [(C.HELP, T.flatten((serverID, settingID), 'ww'))]
        resp = self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        return (description, accepts, returns, notes)

    def getSettingInfoByName(self, serverID, settingName):
        """Get information about a setting using its name."""
        packet = [(C.HELP, T.flatten((serverID, settingName), 'ws')),
                  (C.LOOKUP, T.flatten((serverID, settingName), 'ws'))]
        resp = self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        ID = resp[1][1][1]
        return (description, accepts, returns, notes, ID)

    def _send(self, packet, *args, **kw):
        """Send a request to the manager and wait for the result."""
        return self.cxn.sendRequest(C.MANAGER_ID, packet, *args, **kw).result()

    def _getIDList(self, setting, data=None):
        resp = self._send([(setting, data)])
        names = self._reorderIDList(resp[0][1])
        return names

    def _reorderIDList(self, L):
        return [(name, ID) for ID, name in L]


