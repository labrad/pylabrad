"""Backends for labrad connections

Provides a backend connection that underlies the wrapper client object.
"""

import asyncio
import asyncore
import hashlib
import socket
import sys
import threading
import queue

from labrad import constants as C, errors, thread, types as T
from labrad.stream import packetStream, flattenPacket, flattenRecords, unflattenRecords
from labrad.support import getNodeName, get_password

backends = {}

class BaseConnection(object):
    def __init__(self, name=None):
        self.name = name or 'Python Client (%s)' % getNodeName()
        self.connected = False
        self._nextContext = 1

    def context(self):
        """Create a new context for use with this connection"""
        ctx = 0, self._nextContext
        self._nextContext += 1
        return ctx

    def connect(self, host=C.MANAGER_HOST, port=C.MANAGER_PORT, timeout=C.TIMEOUT, password=None):
        self.host = host
        self.port = port
        if password is None:
            password = get_password()
        self.ID = self._connect(password, timeout)
        self.connected = True

    def disconnect(self):
        if self.connected:
            self._disconnect()
            self.connected = False

    def _connect(self, password=None, timeout=None):
        """Implemented by subclass"""

    def _disconnect(self):
        """Implemented by subclass"""

    def sendRequest(self, target, records, *args, **kw):
        """Implemented by subclass"""

    def sendMessage(self, target, records, *args, **kw):
        """Implemented by subclass"""


class AsyncioConnection(BaseConnection):
    def _connect(self, password, _timeout):
        self.thread = thread.AsyncioThread()
        self.thread.start()
        import time
        time.sleep(1)
        self._next_request = 1
        self.pool = set()
        self.requests = {}
        self.endianness = '>'
        self._server_cache = {}
        self._setting_cache = {}
        self.submit(self._connect_async, self.host, self.port, self.name, password).wait()
        return self.ID

    @asyncio.coroutine
    def _connect_async(self, host, port, name, password):
        self.reader, self.writer = yield from asyncio.open_connection(host=host, port=port)
        self.connected = True

        # start the read loop to listen for incoming packets
        asyncio.async(self._read_loop())

        # send login packet
        resp = yield from self._send_request(C.MANAGER_ID, [])
        challenge = resp[0][1] # get password challenge

        # send password response
        m = hashlib.md5()
        m.update(challenge)
        m.update(password.encode('utf-8'))
        try:
            resp = yield from self._send_request(C.MANAGER_ID, [(0, m.digest(), 's')])
        except Exception:
            raise errors.LoginFailedError('Incorrect password.')
        self.password = C.PASSWORD = password # save password, since it worked
        self.loginMessage = resp[0][1] # get welcome message

        # send identification
        try:
            resp = yield from self._send_request(C.MANAGER_ID, [(0, (1, name), 'ws')])
        except Exception:
            raise errors.LoginFailedError('Bad identification.')
        self.ID = resp[0][1] # get assigned ID

    @asyncio.coroutine
    def _read_loop(self):
        try:
            while True:
                # get packet header (20 bytes)
                hdr = yield from self.reader.readexactly(20)
                context, request, source, length = T.unflatten(hdr, '(ww)iww', endianness='>')

                # get packet data
                data = yield from self.reader.readexactly(length)

                # unflatten the data
                records = unflattenRecords(data, endianness='>')

                self._handle_packet(source, context, request, records)

        except Exception as e:
            # fail any pending requests
            self.connected = False
            for f in self.requests.values():
                f.set_exception(e)
            self.requests.clear()

    def _handle_packet(self, source, context, request, records):
        """Process incoming packet."""
        if request > 0:
            self._handle_request(source, context, request, records)
        elif request < 0:
            self._handle_response(source, context, request, records)
        else:
            self._handle_message(source, context, records)

    def _handle_request(self, source, context, request, records):
        """Process incoming request."""

    def _handle_response(self, source, context, request, records):
        """Process incoming response."""
        if -request in self.requests: # reply has request number negated
            d = self.requests[-request]
            errors = [r[1] for r in records if isinstance(r[1], Exception)]
            if errors:
                # fail on the first error
                d.set_exception(errors[0])
            else:
                d.set_result(records)
        else:
            # probably a response for a request that has already
            # timed out.  If not, something bad has happened.
            print('Invalid response: {}, {}, {}, {}'.format(
                  source, context, request, records))

    def messageReceived(self, source, context, records):
        """Process incoming messages."""
        self._messageLock.run(self._dispatchMessage, source, context, records)

    def _disconnect(self):
        self.submit(self._disconnect_async).wait()
        self.thread.close()

    @asyncio.coroutine
    def _disconnect_async(self):
        self.writer.close()

    def submit(self, func, *args, **kw):
        f = Future()
        @asyncio.coroutine
        def coro():
            try:
                result = yield from func(*args, **kw)
                f.callback(result)
            except Exception as e:
                f.errback(e)
        self.thread.loop.call_soon_threadsafe(asyncio.async, coro())
        return f

    def sendRequest(self, target, records, *args, **kw):
        return self.submit(self._send_request, target, records, *args, **kw)

    def sendMessage(self, target, records, *args, **kw):
        return self.submit(self.send_message, target, records, *args, **kw).wait()


    @asyncio.coroutine
    def _send_message(self, target, records, context=(0, 0)):
        """Send a message to the specified target."""
        target, records = yield from self._lookup_names(target, records)
        yield from self.send_packet(target, context, 0, records)

    @asyncio.coroutine
    def _send_request(self, target, records, context=(0, 0), timeout=None):
        """Send a request to the given target server.

        Returns a deferred that will fire the resulting data packet when
        the request is completed, or will errback if the request times out
        or errors are returned from labrad.  The target server and settings
        may be given either as word IDs or string names.  If necessary,
        any string names will be looked up before the request is sent.
        Lookup results are cached to avoid lookup overhead on subsequent
        requests to the same server or settings.
        """
        target, records = yield from self._lookup_names(target, records)
        resp = yield from self._send_request_no_lookup(target, records, context, timeout)
        return resp

    @asyncio.coroutine
    def _lookup_names(self, server, records):
        """Translate server and setting names into IDs.

        We first attempt to look up these names in the local cache.
        If any are not found there, we fire off a request to the
        Manager to lookup the necessary IDs, and then cache the
        result.
        """
        records = list(records)

        # try to lookup server in cache
        if isinstance(server, str) and server in self._server_cache:
            server = self._server_cache[server]

        # try to lookup settings in cache
        if server in self._setting_cache:
            settings = self._setting_cache[server]
            for i, rec in enumerate(records):
                name = rec[0]
                if isinstance(name, str) and name in settings:
                    records[i] = (settings[name],) + tuple(rec[1:])

        # check to see whether there is still anything to look up
        setting_lookups = [(i, rec[0])
                           for i, rec in enumerate(records)
                           if isinstance(rec[0], str)]
        if isinstance(server, str) or len(setting_lookups):
            # need to do additional lookup here
            if len(setting_lookups):
                indices, names = list(zip(*setting_lookups))
            else:
                indices, names = [], []
            # send the actual lookup request
            recs = [(C.LOOKUP, (server, names), ['w*s', 's*s'])]
            resp = yield from self._send_request_no_lookup(C.MANAGER_ID, recs)
            serverID, IDs = resp[0][1]
            # cache the results
            if isinstance(server, str):
                self._server_cache[server] = serverID
            server = serverID
            settings = self._setting_cache.setdefault(server, {})
            settings.update(list(zip(names, IDs)))
            # update the records for the packet
            for index, ID in zip(indices, IDs):
                records[index] = (ID,) + tuple(records[index][1:])

        return (server, records)

    def clear_cache(self):
        """Clear the cache of looked-up server and settings IDs."""
        self._server_cache = {}
        self._setting_cache = {}

    @asyncio.coroutine
    def _send_request_no_lookup(self, target, records, context=(0, 0), timeout=None):
        """Send a request without doing any lookups of server or setting IDs."""
        if not self.connected:
            raise Exception('Not connected.')
        if len(self.pool):
            n = self.pool.pop()
        else:
            n = self._next_request
            self._next_request += 1

        self.requests[n] = f = asyncio.Future()
        try:
            yield from self._send_packet(target, context, n, records)
            done, _pending = yield from asyncio.wait([f], timeout=timeout)
            if not done:
                raise errors.RequestTimeoutError()
        finally:
            del self.requests[n]
            self.pool.add(n) # reuse request numbers
        return f.result()

    @asyncio.coroutine
    def _send_packet(self, target, context, request, records):
        """Send a raw packet to the specified target."""
        raw = flattenPacket(target, context, request, records, endianness=self.endianness)
        self.writer.write(raw)
        yield from self.writer.drain()

backends['asyncio'] = AsyncioConnection


class AsyncoreConnection(BaseConnection):
    def _connect(self, password, timeout):
        self.connected = False
        self.serverCache = {}
        self.settingCache = {}
        try:
            sock = socket.create_connection((self.host, self.port),
                                            timeout or 5)
            socketMap = {}
            self.cxn = AsyncoreProtocol(sock, map=socketMap)
            self.loop = threading.Thread(target=asyncore.loop,
                kwargs={'timeout':0.01, 'map': socketMap})
            self.loop.daemon = True
            self.loop.start()
            try:
                return self.login(password, self.name)
            except Exception as e:
                self.disconnect()
                raise
        except errors.LoginFailedError:
            raise
        except Exception as e:
            raise errors.LoginFailedError(e)

    def _disconnect(self):
        self.cxn.drop()
        self.loop.join()

    def login(self, password, *ident):
        # send login packet
        resp = self.sendRequest(C.MANAGER_ID, []).wait()
        challenge = resp[0][1] # get password challenge

        # send password response
        if password is None:
            password = get_password()
        m = hashlib.md5()
        m.update(challenge)
        m.update(password.encode('utf-8'))
        try:
            resp = self.sendRequest(C.MANAGER_ID, [(0, m.digest(), 's')]).wait()
        except Exception:
            raise errors.LoginFailedError('Incorrect password.')
        self.loginMessage = resp[0][1] # get welcome message

        # send identification
        try:
            resp = self.sendRequest(C.MANAGER_ID, [(0, (1,) + ident, 'w' + 's' * len(ident))]).wait()
        except Exception:
            raise errors.LoginFailedError('Bad identification.')
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
                indices, names = list(zip(*settingLookups))
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


#backends['asyncore'] = AsyncoreConnection

class AsyncoreProtocol(asyncore.dispatcher):
    """Receive and send labrad packets."""

    def __init__(self, socket, **kw):
        asyncore.dispatcher.__init__(self, socket, **kw)

        self.alive = True
        self.lock = threading.RLock()
        self.nextRequest = 1
        self.requests = {}
        self.pool = set()
        self.queue = queue.Queue()
        self.buffer = b''

        # create a generator to assemble the packets
        self.stream = packetStream(self.handleResponse)
        next(self.stream) # start the packet stream

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
        try:
            self.close()
        finally:
            self.flushCommands()
            for d in list(self.requests.values()):
                d.errback(reason)

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
            except queue.Empty:
                break
            if command is None:
                self.terminate('Connection closed')
                return False
            elif isinstance(command, bytes):
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

    def handleResponse(self, _source, _context, request, records):
        n = -request # reply has request number negated
        if n not in self.requests:
            # probably a response for a request that has already
            # timed out.  If a message or incoming request, we
            # simply ignore it, since these shouldn't happen.
            return
        future = self.requests[n]
        del self.requests[n]
        self.pool.add(n)
        errors = [r[1] for r in records if isinstance(r[1], Exception)]
        if errors:
            # fail on the first error
            future.errback(errors[0])
        else:
            future.callback(records)


class Failure(object):
    def __init__(self, error=None):
        if error is None:
            self.value = sys.exc_info()[1]
        else:
            self.value = error

    def raiseException(self):
        raise self.value

class Future(object):

    ready = queue.Queue()

    def __init__(self):
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
        self.ready.put(self)

    def errback(self, error=None):
        if not hasattr(error, 'raiseException'):
            error = Failure(error)
        self.result = error
        self.ready.put(self)

    def wait(self):
        if self.done:
            return self.result
        while True:
            f = self.ready.get()
            f.done = True
            result = f.result
            if hasattr(result, 'raiseException'):
                # this can be a Twisted Failure or our
                # own Failure class, as defined above
                # If any Future in the queue fails,
                # we immediately bail.
                result.raiseException()
            else:
                for func, args, kw in f.callbacks:
                    result = func(result, *args, **kw)
                f.result = result
            if f is self:
                return result

    def __repr__(self):
        if self.done:
            return '<Future: result=%r>' % (self.result,)
        else:
            return '<Future: pending...>'


def connect(host=C.MANAGER_HOST, port=C.MANAGER_PORT, name=None, backend=None, **kw):
    """Create a backend connection to labrad"""
    if backend is None:
        if 'asyncio' in backends:
            backend = 'asyncio'
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
        return self._getIDList(C.SERVERS_LIST)

    def getServerInfo(self, serverID):
        """Get information about a server."""
        packet = [(C.HELP, serverID, 'w'),
                  (C.SETTINGS_LIST, serverID, 'w')]
        resp = self._send(packet)
        descr, notes = resp[0][1]
        settings = self._reorderIDList(resp[1][1])
        return (descr.decode('utf-8'), notes.decode('utf-8'), settings)

    def getSettingsList(self, serverID):
        """Get list of settings for a server."""
        return self._getIDList(C.SETTINGS_LIST, serverID)

    def getSettingInfo(self, serverID, settingID):
        """Get information about a setting."""
        packet = [(C.HELP, (serverID, settingID), 'ww')]
        resp = self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        return (
            description.decode('utf-8'),
            [a.decode('utf-8') for a in accepts],
            [r.decode('utf-8') for r in returns],
            notes.decode('utf-8')
        )

    def _send(self, packet, *args, **kw):
        """Send a request to the manager and wait for the result."""
        return self.cxn.sendRequest(C.MANAGER_ID, packet, *args, **kw).wait()

    def _getIDList(self, setting, data=None):
        resp = self._send([(setting, data)])
        names = self._reorderIDList(resp[0][1])
        return names

    def _reorderIDList(self, L):
        return [(name.decode('utf-8'), ID) for ID, name in L]


