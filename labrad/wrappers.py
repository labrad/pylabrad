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

from labrad import constants as C, types as T, protocol, util
from labrad.util import mangle, indent, MultiDict, extractKey
from labrad.manager import ILabradManager

from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

class AsyncSettingWrapper(object):
    def __init__(self, server, name, labrad_name, ID):
        self.name = self.__name__ = name
        self.ID = ID
        self._labrad_name = labrad_name
        self._server = server
        self._mgr = server._mgr

    def refresh(self):
        return self._refresh()

    @inlineCallbacks
    def _refresh(self):
        info = yield self._mgr.getSettingInfo(self._server.ID, self.ID)
        self.__doc__, self.accepts, self.returns, self.notes = info
        self._num_listeners = 0

    def __call__(self, *args, **kwargs):
        wrap = extractKey(kwargs, 'wrap', True)
        if not len(args):
            args = None
        elif len(args) == 1:
            args = args[0]
        resp = self._server._send((self.ID, args, self.accepts), **kwargs)
        if wrap:
            resp.addCallback(lambda resp: resp[0][1])
        return resp
    
    def connect(self, handler, *args):
        srv = self._server
        srv._cxn._cxn.addListener((srv.ID, self.ID), handler)
        self._num_listeners += 1
        if self._num_listeners == 1:
            # TODO: remove listener if registration fails
            return self.__call__(self.ID, *args)
        else:
            return defer.succeed(None)
    
    def disconnect(self, handler):
        srv = self._server
        srv._cxn._cxn.removeListener((srv.ID, self.ID), handler)
        self._num_listeners -= 1
        if self._num_listeners == 0:
            return self.__call__()
        else:
            return defer.succeed(None)

class AsyncPacketWrapper(object):
    """An object to encapsulate a labrad packet to a server."""
    
    def __init__(self, server, **kwargs):
        self.settings = MultiDict()
        self._server = server
        self._packet = []
        self._kwargs = kwargs

        for name in server.settings:
            s = server.settings[name]
            name, labrad_name, ID = s.name, s._labrad_name, s.ID
            wrapped = self._wrap(s)
            wrapped.name = name
            setattr(self, name, wrapped)
            self.settings[name, labrad_name, ID] = wrapped

    def send(self, **kwargs):
        """Send this packet to the server."""
        kw = dict(self._kwargs)
        kw.update(kwargs)
        #print 'sending packet:', self._packet
        records = [rec[:3] for rec in self._packet]
        #print 'records:', records
        resp = self._server._send(records, **kw)
        resp.addCallback(PacketResponse, self._server, self._packet)
        return resp

    def __getitem__(self, key):
        return self.settings[key]

    def __setitem__(self, key, value):
        """Update existing parts of the packet, indexed by key."""
        for i, (ID, data, accepts, rkey) in enumerate(self._packet):
            if key == rkey:
                self._packet[i] = ID, value, accepts, key

    def _wrap(self, setting):
        ID, accepts, name = setting.ID, setting.accepts, setting.name
        def wrapped(*args, **kwargs):
            key = extractKey(kwargs, 'key', None)
            if not len(args):
                args = None
            elif len(args) == 1:
                args = args[0]
            self._packet.append((ID, args, accepts, key))
            return self
        return wrapped

class AsyncServerWrapper:
    def __init__(self, cxn, name, labrad_name, ID, **kw):
        self._cxn = cxn
        self._mgr = cxn._mgr
        self.ID = ID
        self.name = name
        self.settings = MultiDict()
        self._labrad_name = labrad_name
        self._kw = kw

    def refresh(self):
        return self._refresh()

    @inlineCallbacks
    def _refresh(self):
        """Update the list of available settings for this server."""

        # get a list of the currently-available settings
        info = yield self._mgr.getServerInfo(self.ID)
        self.__doc__, self.notes, slist = info
        names, labrad_names, IDs = zip(*slist)
        names = [self._fixName(n) for n in names]
        slist = zip(names, labrad_names, IDs)

        # determine what to add, update and delete to be current
        additions = [s for s in slist if s[0] not in self.settings]
        refreshes = [n for n in self.settings if n in names]
        deletions = [n for n in self.settings if n not in names]

        actions = [self._addSetting(*s) for s in additions] +\
                  [self._refreshSetting(n) for f in refreshes] +\
                  [self._delSetting(n) for n in deletions]
        yield defer.DeferredList(actions, fireOnOneErrback=True)
        returnValue(self.settings)

    _staticAttrs = ['settings', 'refresh', 'context', 'packet']
    
    def _fixName(self, name):
        if name in self._staticAttrs:
            name = 'lr_' + name
        return name

    @inlineCallbacks
    def _addSetting(self, name, labrad_name, ID):
        setting = yield wrapAsync(
            self._settingWrapper, self, name, labrad_name, ID)
        self.settings[name, labrad_name, ID] = setting
        setattr(self, name, setting)

    def _refreshSetting(self, name):
        setting = getattr(self, name)
        return setting._refresh()

    def _delSetting(self, name):
        if hasattr(self, name):
            delattr(self, name)
            del self.settings[name]
        return defer.succeed(None)

    _settingWrapper = AsyncSettingWrapper
    _packetWrapper = AsyncPacketWrapper

    def context(self):
        return self._cxn.context()

    def packet(self, **kwargs):
        return self._packetWrapper(self, **kwargs)

    def __call__(self):
        return self
        # TODO: this should make a clone that can have different
        # default keyword args, and, in particular, should talk
        # to the server in a different context

    def __getitem__(self, key):
        return self.settings[key]

    def _send(self, *args, **kwargs):
        """Send packet to this server."""
        return self._cxn._send(self.ID, *args, **kwargs)


def connectAsync(host=C.MANAGER_HOST, port=C.MANAGER_PORT,
                 name='Python Client'):
    cxn = AsyncClient(name)
    return cxn.connect(host, port)


class AsyncClient:
    def __init__(self, name):
        self.name = name
        self.connected = False
        self.servers = MultiDict()
        self._next_context = 1
        self._disconnectWaiters = []
        self._factory = protocol.labradClientFactory(self.name)

    _staticAttrs = ['connect', 'notifyOnDisconnect',
                    'disconnect', 'refresh', 'context']

    @inlineCallbacks
    def connect(self, host, port, timeout=C.TIMEOUT):
        """Connect to the labrad manager."""
        reactor.connectTCP(host, port, self._factory, timeout)
        self._cxn = yield self._factory.getConnection()
        self._mgr = ILabradManager(self._cxn)

        self.host = host
        self.port = port
        self.connected = True
        yield self._refresh()
        returnValue(self)

    def notifyOnDisconnect(self):
        return self._factory.notifyOnDisconnect()

    def disconnect(self):
        if self.connected:
            self._cxn.disconnect()
            self.connected = False

    def refresh(self):
        return self._refresh()

    @inlineCallbacks
    def _refresh(self):
        """Update the list of available labrad servers."""
        
        # get a list of the currently-available servers
        slist = yield self._mgr.getServersList()
        names, labrad_names, IDs = zip(*slist)
        names = [self._fixName(n) for n in names]
        slist = zip(names, labrad_names, IDs)

        # determine what to add, update and delete to be current
        additions = [s for s in slist if s[0] not in self.servers]
        refreshes = [n for n in self.servers if n in names]
        deletions = [n for n in self.servers if n not in names]

        actions = [self._addServer(*s) for s in additions] +\
                  [self._refreshServer(n) for f in refreshes] +\
                  [self._delServer(n) for n in deletions]
        yield defer.DeferredList(actions, fireOnOneErrback=True)
        returnValue(self.servers)

    def _fixName(self, name):
        if name in self._staticAttrs:
            name = 'labrad_' + name
        return name

    @inlineCallbacks
    def _addServer(self, name, labrad_name, ID):
        server = yield wrapAsync(
            self._serverWrapper, self, name, labrad_name, ID)
        self.servers[name, labrad_name, ID] = server
        setattr(self, name, server)

    def _refreshServer(self, name):
        if hasattr(self, name):
            server = getattr(self, name)
            return server._refresh()
        return defer.succeed(None)

    def _delServer(self, name):
        if hasattr(self, name):
            delattr(self, name)
            del self.servers[name]
        return defer.succeed(None)

    _serverWrapper = AsyncServerWrapper

    def context(self):
        context = (0, self._next_context)
        self._next_context += 1
        return context

    def __getitem__(self, key):
        return self.servers[key]
            
    def _send(self, target, records, *args, **kwargs):
        """Send a packet over this connection."""
        return self._cxn.request(target, records, *args, **kwargs)


class AsyncClientAdapter:
    """Adapt a LabRAD request protocol object to an asynchronous client."""
    def __init__(self, prot):
        self.servers = MultiDict()
        self._cxn = prot
        self._mgr = ILabradManager(self._cxn)
        self._next_context = 1

    _staticAttrs = ['refresh', 'context']

    def refresh(self):
        return self._refresh()

    @inlineCallbacks
    def _refresh(self):
        """Update the list of available labrad servers."""
        
        # get a list of the currently-available servers
        slist = yield self._mgr.getServersList()
        names, labrad_names, IDs = zip(*slist)
        names = [self._fixName(n) for n in names]
        slist = zip(names, labrad_names, IDs)

        # determine what to add, update and delete to be current
        additions = [s for s in slist if s[0] not in self.servers]
        refreshes = [n for n in self.servers if n in names]
        deletions = [n for n in self.servers if n not in names]

        actions = [self._addServer(*s) for s in additions] +\
                  [self._refreshServer(n) for f in refreshes] +\
                  [self._delServer(n) for n in deletions]
        yield defer.DeferredList(actions, fireOnOneErrback=True)
        returnValue(self.servers)

    def _fixName(self, name):
        if name in self._staticAttrs:
            name = 'lr_' + name
        return name

    @inlineCallbacks
    def _addServer(self, name, labrad_name, ID):
        server = yield wrapAsync(
            self._serverWrapper, self, name, labrad_name, ID)
        self.servers[name, labrad_name, ID] = server
        setattr(self, name, server)

    def _refreshServer(self, name):
        server = getattr(self, name)
        return server._refresh()

    def _delServer(self, name):
        if hasattr(self, name):
            delattr(self, name)
            del self.servers[name]
        return defer.succeed(None)

    _serverWrapper = AsyncServerWrapper

    def context(self):
        context = (0, self._next_context)
        self._next_context += 1
        return context

    def __getitem__(self, key):
        return self.servers[key]

    def _send(self, target, records, *args, **kwargs):
        """Send a packet over this connection."""
        return self._cxn.request(target, records, *args, **kwargs)


def wrapAsync(cls, *args, **kwargs):
    obj = cls(*args, **kwargs)
    d = obj._refresh()
    d.addCallback(lambda x: obj)
    return d


class PacketResponse(object):
    """Wrapper for response packets from labrad servers.

    Methods are added to access the records in this response packet
    coming from each setting.
    """
    def __init__(self, resp, server, packet):
        self.settings = MultiDict()
        index = 0
        for (pID, pData, pAccepts, key), (ID, data) in zip(packet, resp):
            setting = server.settings[ID]
            name, labrad_name = setting.name, setting._labrad_name
            # if this record has a key, index by key only
            # otherwise by setting name, labrad name and ID
            if key:
                name = labrad_name = ID = key
            if hasattr(self, name):
                l = getattr(self, name)
            else:
                l = []
                setattr(self, name, l)
                self.settings[name, labrad_name, ID] = l
            l.append(data)
        # if setting has only one response, unwrap it from the list
        for name, resp in self.settings.items():
            if len(resp) == 1:
                setattr(self, name, resp[0])
                self.settings[name] = resp[0]

    def __getitem__(self, key):
        return self.settings[key]

