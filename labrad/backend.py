"""Backends for labrad connections

Provides a backend connection that underlies the wrapper client object.
"""

from __future__ import absolute_import

import threading

from concurrent.futures import Future
from twisted.internet import defer, reactor

from labrad import auth, constants as C, support, thread, types as T
from labrad.wrappers import getConnection


class TwistedConnection(object):
    def __init__(self, name=None):
        self.name = name or 'Python Client ({})'.format(support.getNodeName())
        self._connected = threading.Event()
        self._nextContext = 1

    def connect(self, host=C.MANAGER_HOST, port=None, timeout=C.TIMEOUT,
                password=None, tls_mode=C.MANAGER_TLS, username=None,
                headless=False):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls_mode = tls_mode
        self.username = username
        self.password = password
        self.headless = headless

        @defer.inlineCallbacks
        def _connect_deferred():
            cxn = yield getConnection(self.host, self.port, self.name,
                                      password, tls_mode=tls_mode,
                                      username=username, headless=headless)
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

        thread.startReactor()
        self.cxn = self.call(_connect_deferred).result()
        self.ID = self.cxn.ID

    @property
    def connected(self):
        return self._connected.is_set()

    def disconnect(self):
        if self.connected:
            self.call(self.cxn.disconnect).result()

    def spawn(self):
        """Start a new independent backend connection to the same manager."""
        cls = self.__class__
        inst = cls(name=self.name)
        inst.connect(host=self.host, port=self.port, timeout=self.timeout,
                     password=self.password, tls_mode=self.tls_mode,
                     username=self.username, headless=self.headless)
        return inst

    def context(self):
        """Create a new context for use with this connection"""
        ctx = 0, self._nextContext
        self._nextContext += 1
        return ctx

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


def connect(host=C.MANAGER_HOST, port=None, name=None, **kw):
    """Create a backend connection to labrad"""
    cxn = TwistedConnection(name)
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


