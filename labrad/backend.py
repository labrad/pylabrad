"""Backends for labrad connections

Provides a backend connection that underlies the wrapper client object.
"""

import asyncio
from concurrent import futures
import hashlib

from labrad import constants as C, errors, thread, types as T
from labrad.stream import flattenPacket, unflattenRecords
from labrad.support import getNodeName, get_password

backends = {}

class BaseConnection():
    def __init__(self, name=None):
        self.name = name or 'Python Client (%s)' % getNodeName()
        self.connected = False
        self._next_context = 1

    def context(self):
        """Create a new context for use with this connection"""
        ctx = 0, self._next_context
        self._next_context += 1
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

    def send_request(self, target, records, *args, **kw):
        """Implemented by subclass"""

    def send_message(self, target, records, *args, **kw):
        """Implemented by subclass"""


class AsyncioConnection(BaseConnection):
    def _connect(self, password, _timeout):
        self._executor = thread.AsyncioExecutor.get()
        self._next_request = 1
        self.pool = set()
        self.requests = {}
        self.endianness = '>'
        self._server_cache = {}
        self._setting_cache = {}
        self.submit(self._connect_async, self.host, self.port, self.name, password).result()
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

    @asyncio.coroutine
    def message_received(self, source, context, records):
        """Process incoming messages."""
        with (yield from self._message_lock):
            self._dispatch_message(source, context, records)

    def _disconnect(self):
        self.submit(self._disconnect_async).result()

    @asyncio.coroutine
    def _disconnect_async(self):
        self.writer.close()

    def submit(self, func, *args, **kw):
        return self._executor.submit(func, *args, **kw)

    def send_request(self, target, records, *args, **kw):
        return self.submit(self._send_request, target, records, *args, **kw)

    def send_message(self, target, records, *args, **kw):
        return self.submit(self.send_message, target, records, *args, **kw).result()


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
            result = yield from asyncio.wait_for(f, timeout=timeout)
            return result
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


def connect(host=C.MANAGER_HOST, port=C.MANAGER_PORT, name=None, backend=None, **kw):
    """Create a backend connection to labrad"""
    if backend is None:
        backend = 'asyncio'
    cxn = backends[backend](name)
    cxn.connect(host, port, **kw)
    return cxn


class ManagerService:
    """Wraps a backend connection to provide a basic synchronous interface to the Manager."""
    def __init__(self, cxn):
        self.cxn = cxn

    def get_servers_list(self):
        """Get list of connected servers."""
        return self._get_id_list(C.SERVERS_LIST)

    def get_server_info(self, serverID):
        """Get information about a server."""
        packet = [(C.HELP, serverID, 'w'),
                  (C.SETTINGS_LIST, serverID, 'w')]
        resp = self._send(packet)
        descr, notes = resp[0][1]
        settings = self._reorder_id_list(resp[1][1])
        return (descr.decode('utf-8'), notes.decode('utf-8'), settings)

    def get_settings_list(self, serverID):
        """Get list of settings for a server."""
        return self._get_id_list(C.SETTINGS_LIST, serverID)

    def get_setting_info(self, serverID, settingID):
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
        return self.cxn.send_request(C.MANAGER_ID, packet, *args, **kw).result()

    def _get_id_list(self, setting, data=None):
        resp = self._send([(setting, data)])
        names = self._reorder_id_list(resp[0][1])
        return names

    def _reorder_id_list(self, L):
        return [(name.decode('utf-8'), ID) for ID, name in L]


