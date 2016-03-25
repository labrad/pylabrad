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
import labrad.types as T

from labrad import constants as C, crypto, errors, support, util
from labrad.stream import packetStream, flattenPacket


class LabradProtocol(protocol.Protocol):
    """Receive and send labrad packets."""

    def __init__(self):
        self.disconnected = False
        self._nextRequest = 1
        self.pool = set()
        self.requests = {}
        self.listeners = {}
        self._messageLock = defer.DeferredLock()
        self.clearCache()
        self.endianness = '>'
        self.request_handler = None
        # create a generator to assemble the packets
        self.packetStream = packetStream(self.packetReceived, self.endianness)
        self.packetStream.next() # start the packet stream

        self.onDisconnect = util.DeferredSignal()

    def set_address(self, host, port):
        """Store host and port of remote endpoint in protocol object.

        This is called by the connect function below after successfully
        establishing a connection. The host and port are used to cache our
        credentials after we authenticate successfully.

        Args:
            host (str): The hostname we are connected to.
            port (int): The TCP port number we are connected to.
        """
        self.host = host
        self.port = port

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
        raw = flattenPacket(target, context, request, records, endianness=self.endianness)
        self.transport.write(raw)

    @inlineCallbacks
    def sendMessage(self, target, records, context=(0, 0)):
        """Send a message to the specified target."""
        target, records = yield self._lookupNames(target, records)
        self.sendPacket(target, context, 0, records)

    @inlineCallbacks
    def sendRequest(self, target, records, context=(0, 0), timeout=None, unflatten=True):
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
        resp = yield self._sendRequestNoLookup(target, records, context, timeout, unflatten)
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

    def unflattenResponse(self, response_records):
        return [(ID, data.unflatten()) for (ID, data) in response_records]

    def _sendRequestNoLookup(self, target, records, context=(0, 0), timeout=None, unflatten=True):
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
        if unflatten:
            d.addCallback(self.unflattenResponse)
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

    @inlineCallbacks
    def requestReceived(self, source, context, request, flat_records):
        """Process incoming request."""
        try:
            if self.request_handler is None:
                log.msg('server request_handler not set')
                raise Exception('server request_handler not set')
            response = yield self.request_handler(source, context, flat_records)
            self.sendPacket(source, context, -request, response)
        except Exception as e:
            # this will only happen if there was a problem while sending,
            # which usually means a problem flattening the response into
            # a valid LabRAD packet
            self.sendPacket(source, context, -request, [(0, e)])

    def responseReceived(self, source, context, request, flat_records):
        """Process incoming response."""
        if -request in self.requests: # reply has request number negated
            d = self.requests[-request]
            errors = [r[1].unflatten() for r in flat_records if isinstance(r[1].tag, T.LRError)]
            if errors:
                # fail on the first error
                d.errback(errors[0])
            else:
                d.callback(flat_records)
        else:
            # probably a response for a request that has already
            # timed out.  If not, something bad has happened.
            log.msg('Invalid response: %s, %s, %s, %s' % \
                    (source, context, request, records))

    def messageReceived(self, source, context, flat_records):
        """Process incoming messages."""
        self._messageLock.run(self._dispatchMessage, source, context, flat_records)

    @inlineCallbacks
    def _dispatchMessage(self, source, context, flat_records):
        """Dispatch a message to all matching listeners."""
        for ID, flat_data in flat_records:
            data = flat_data.unflatten()
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

    @inlineCallbacks
    def authenticate(self, password):
        """Authenticate to the manager using the given password."""
        # send login packet
        resp = yield self.sendRequest(C.MANAGER_ID, [])
        challenge = resp[0][1] # get password challenge

        if password is None:
            password = support.get_password(self.host, self.port)

        # send password response
        m = hashlib.md5()
        m.update(challenge)
        m.update(password)
        try:
            resp = yield self.sendRequest(C.MANAGER_ID, [(0L, m.digest())])
        except Exception:
            raise errors.LoginFailedError('Incorrect password.')
        support.cache_password(self.host, self.port, password)
        self.password = password
        self.loginMessage = resp[0][1] # get welcome message

    def loginClient(self, name):
        """Log in as a client by sending our name to the manager.

        Args:
            name (str): The name of this labrad connection. Need not be unique.

        Returns:
            twisted.internet.defer.Deferred(None): A deferred that will fire
            after we have logged in.
        """
        return self._doLogin(name)

    def loginServer(self, name, descr, notes):
        """Log in as a server by sending our name and metadata to the manager.

        Args:
            name (str): The name of this server. Must be unique; login will
                fail if another server of the same name is already connected.
            descr (str): A description of this server, which will be exposed
                to other labrad clients.
            notes (str): More descriptive information about the server. This
                field is deprecated; instead we recommend just putting all info
                into descr.

        Returns:
            twisted.internet.defer.Deferred(None): A deferred that will fire
            after we have logged in.
        """
        return self._doLogin(name, descr, notes)

    @inlineCallbacks
    def _doLogin(self, *ident):
        # send identification
        resp = yield self.sendRequest(C.MANAGER_ID, [(0L, (1L,) + ident)])
        self.ID = resp[0][1] # get assigned ID


class MessageContext(object):
    """Object to be passed as the first argument to message handlers."""

    def __init__(self, source, context, target):
        self.source = source
        self.ID = context
        self.target = target

    def __repr__(self):
        return 'MessageContext(source=%s, ID=%s, target=%s)' % (self.source, self.ID, self.target)


# factory for creating LabRAD connections
_factory = protocol.ClientCreator(reactor, LabradProtocol)


@inlineCallbacks
def connect(host=C.MANAGER_HOST, port=None, tls_mode=C.MANAGER_TLS):
    """Connect to LabRAD and return a deferred that fires the protocol object.

    Args:
        host (str): The hostname of the manager.
        port (int): The tcp port of the manager. If None, use the appropriate
            default value based on the TLS mode.
        tls_mode (str): The tls mode to use for this connection. See:
            `labrad.constants.check_tls_mode`.

    Returns:
        twisted.internet.defer.Deferred(LabradProtocol): A deferred that will
        fire with the protocol once the connection is established.
    """
    tls_mode = C.check_tls_mode(tls_mode)
    if port is None:
        port = C.MANAGER_PORT_TLS if tls_mode == 'on' else C.MANAGER_PORT

    if tls_mode == 'on':
        tls_options = crypto.tls_options(host)
        p = yield _factory.connectSSL(host, port, tls_options, timeout=C.TIMEOUT)
        p.set_address(host, port)
        returnValue(p)

    @inlineCallbacks
    def do_connect():
        p = yield _factory.connectTCP(host, port, timeout=C.TIMEOUT)
        p.set_address(host, port)
        returnValue(p)

    @inlineCallbacks
    def start_tls(p, cert_string=None):
        try:
            resp = yield p.sendRequest(C.MANAGER_ID, [(1L, ('STARTTLS', host))])
        except Exception:
            raise Exception(
                'Failed sending STARTTLS command to server. You should update '
                'the manager and configure it to support encryption or else '
                'disable encryption for clients. See '
                'https://github.com/labrad/pylabrad/blob/master/CONFIG.md')
        cert = resp[0][1]
        p.transport.startTLS(crypto.tls_options(host, cert_string=cert_string))
        returnValue(cert)

    def ping(p):
        return p.sendRequest(C.MANAGER_ID, [(2L, 'PING')])

    p = yield do_connect()
    is_local_connection = util.is_local_connection(p.transport)
    if ((tls_mode == 'starttls-force') or
        (tls_mode == 'starttls' and not is_local_connection)):
        try:
            cert = yield start_tls(p)
        except Exception:
            # TODO: remove this retry. This is a temporary fix to support
            # compatibility until TLS is fully deployed.
            print ('STARTTLS failed; will retry without encryption in case we '
                   'are connecting to a legacy manager.')
            p = yield connect(host, port, tls_mode='off')
            print 'Connected without encryption.'
            returnValue(p)
        try:
            yield ping(p)
        except Exception:
            print 'STARTTLS failed due to untrusted server certificate:'
            print 'SHA1 Fingerprint={}'.format(crypto.fingerprint(cert))
            print
            while True:
                ans = raw_input(
                        'Accept server certificate for host "{}"? (accept just '
                        'this [O]nce; [S]ave and always accept this cert; '
                        '[R]eject) '.format(host))
                ans = ans.lower()
                if ans in ['o', 's', 'r']:
                    break
                else:
                    print 'Invalid input:', ans
            if ans == 'r':
                raise
            p = yield do_connect()
            yield start_tls(p, cert)
            yield ping(p)
            if ans == 's':
                # save now that we know TLS succeeded,
                # including hostname verification.
                crypto.save_cert(host, cert)
    returnValue(p)
