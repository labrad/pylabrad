"""Backends for labrad connections

Provides a backend connection that underlies the wrapper client object.
"""

from __future__ import absolute_import

import threading

from concurrent.futures import Future
from twisted.internet import defer, reactor

from labrad import concurrent, constants as C, support, thread, types as T
from labrad.wrappers import getConnection


class TwistedConnection(object):
    def __init__(self, cxn, spawn_kw=None):
        """Create a synchronous wrapper around an asynchronous connection.

        Args:
            cxn (labrad.protocol.LabradProtocol): The asynchronous protocol
                instance for which to provide a synchronous interface.
            spawn_kw (dict): Keyword arguments to pass to labrad.backend.connect
                to spawn a new connection. If None, spawning will fail.
        """
        self.cxn = cxn
        self.name = cxn.name
        self.ID = cxn.ID
        self.host = cxn.host
        self.port = cxn.port
        self._spawn_kw = spawn_kw
        self._connected = threading.Event()
        self._connected.set()

        # Setup a coroutine that will clear the connected flag when the
        # connection is lost. We launch this but do not wait for the result of
        # the future because we want this to happen asynchronously in the
        # background.
        @defer.inlineCallbacks
        def handle_disconnect():
            try:
                yield cxn.onDisconnect()
            except Exception:
                pass
            self._connected.clear()
        concurrent.call_future(handle_disconnect)

    @property
    def connected(self):
        return self._connected.is_set()

    def disconnect(self):
        if self.connected:
            concurrent.call_future(self.cxn.disconnect).result()

    def spawn(self):
        """Start a new independent backend connection to the same manager."""
        if self._spawn_kw is None:
            raise ValueError("Cannot spawn from {}".format(self))
        return connect(**self._spawn_kw)

    def context(self):
        """Create a new context for use with this connection"""
        return concurrent.call_future(self.cxn.context).result()

    def sendRequest(self, target, records, *args, **kw):
        return concurrent.call_future(self.cxn.sendRequest, target, records,
                                      *args, **kw)

    def sendMessage(self, target, records, *args, **kw):
        return concurrent.call_future(self.cxn.sendMessage, target, records,
                                      *args, **kw).result()


def connect(host=C.MANAGER_HOST, port=None, name=None, timeout=C.TIMEOUT, **kw):
    """Create a backend connection to labrad.

    This connects to labrad asynchronously and then wraps the underlying async
    connection object in a synchronous TwistedConnection interface.
    """
    name = name or 'Python Client ({})'.format(support.getNodeName())

    thread.startReactor()
    future = concurrent.call_future(getConnection, host, port, name, **kw)
    cxn = future.result(timeout=timeout)

    # Make a dict of all params we were called with so that identical new
    # connections can be spawned from this one.
    spawn_kw = dict(host=host, port=port, name=name, timeout=timeout, **kw)

    return TwistedConnection(cxn, spawn_kw=spawn_kw)


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


