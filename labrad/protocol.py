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

import asyncio
import hashlib

from labrad import constants as C, errors, stream, types as T


class AsyncioConnection:

    def __init__(self, reader, writer, delegate):
        self.reader = reader
        self.writer = writer
        self.delegate = delegate
        self._next_request = 1
        self.pool = set()
        self.requests = {}
        self.endianness = '>'
        self._server_cache = {}
        self._setting_cache = {}
        self._message_lock = asyncio.Lock()

    # login protocol
    def login_client(self, password, name):
        """Log in as a client."""
        return self._do_login(password, (1, name,), 'ws')

    def login_server(self, password, name, descr, notes):
        """Log in as a server."""
        return self._do_login(password, (1, name, descr, notes), 'wsss')

    @asyncio.coroutine
    def _do_login(self, password, ident, ident_t):
        self.connected = True

        # start the read loop to listen for incoming packets
        asyncio.async(self.read_loop())

        # send login packet
        resp = yield from self.send_request(C.MANAGER_ID, [])
        challenge = resp[0][1] # get password challenge

        # send password response
        m = hashlib.md5()
        m.update(challenge)
        m.update(password.encode('utf-8'))
        try:
            resp = yield from self.send_request(C.MANAGER_ID, [(0, m.digest(), 's')])
        except Exception:
            raise errors.LoginFailedError('Incorrect password.')
        self.password = C.PASSWORD = password # save password, since it worked
        self.loginMessage = resp[0][1] # get welcome message

        # send identification
        try:
            resp = yield from self.send_request(C.MANAGER_ID, [(0, ident, ident_t)])
        except Exception:
            raise errors.LoginFailedError('Bad identification.')
        self.ID = resp[0][1] # get assigned ID

    @asyncio.coroutine
    def read_loop(self):
        try:
            while True:
                # get packet header (20 bytes)
                hdr = yield from self.reader.readexactly(20)
                context, request, source, length = T.unflatten(hdr, '(ww)iww', endianness='>')

                # get packet data
                data = yield from self.reader.readexactly(length)

                # unflatten the data
                records = stream.unflattenRecords(data, endianness='>')

                # handle packet asynchronously
                if request > 0:
                    asyncio.async(self.handle_request(source, context, request, records))
                elif request < 0:
                    asyncio.async(self.handle_response(source, context, request, records))
                else:
                    asyncio.async(self.handle_message(source, context, records))

        except Exception as e:
            # fail any pending requests
            self.connected = False
            for f in self.requests.values():
                f.set_exception(e)
            self.requests.clear()
            self.writer.close()

    @asyncio.coroutine
    def handle_request(self, source, context, request, records):
        """Process incoming request."""
        try:
            response = yield from self.delegate.handle_request(source, context, records)
            yield from self.send_packet(source, context, -request, response)
        except Exception as e:
            import traceback
            traceback.print_exc()
            # this will only happen if there was a problem while sending,
            # which usually means a problem flattening the response into
            # a valid LabRAD packet
            yield from self.send_packet(source, context, -request, [(0, e)])

    @asyncio.coroutine
    def handle_response(self, source, context, request, records):
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
            print('Invalid response:', source, context, request, records)

    @asyncio.coroutine
    def handle_message(self, source, context, records):
        """Process incoming messages."""
        with (yield from self._message_lock):
            self._dispatch_message(source, context, records)

    @asyncio.coroutine
    def close(self):
        self.writer.close()

    def _dispatch_message(self, *a, **kw):
        pass

    def add_listener(self, *a, **kw):
        pass

    def remove_listener(self, *a, **kw):
        pass

    @asyncio.coroutine
    def send_message(self, target, records, context=(0, 0)):
        """Send a message to the specified target."""
        target, records = yield from self._lookup_names(target, records)
        yield from self.send_packet(target, context, 0, records)

    @asyncio.coroutine
    def send_request(self, target, records, context=(0, 0), timeout=None):
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
            yield from self.send_packet(target, context, n, records)
            result = yield from asyncio.wait_for(f, timeout=timeout)
            return result
        finally:
            del self.requests[n]
            self.pool.add(n) # reuse request numbers
        return f.result()

    @asyncio.coroutine
    def send_packet(self, target, context, request, records):
        """Send a raw packet to the specified target."""
        raw = stream.flattenPacket(target, context, request, records, endianness=self.endianness)
        self.writer.write(raw)
        yield from self.writer.drain()


class MessageContext():
    """Object to be passed as the first argument to message handlers."""

    def __init__(self, source, context, target):
        self.source = source
        self.ID = context
        self.target = target

    def __repr__(self):
        return 'MessageContext(source=%s, ID=%s, target=%s)' % (self.source, self.ID, self.target)
