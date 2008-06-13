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
from labrad.protocol import LabradProtocol
from labrad.interfaces import ILabradProtocol, ILabradManager, IClientAsync
from labrad.util import mangle, indent, MultiDict, extractKey

from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.components import registerAdapter

from zope.interface import implements

class AsyncSettingWrapper(object):
    """Represents a setting on a remote LabRAD server."""
    
    def __init__(self, server, name, labrad_name, ID):
        self.name = self.__name__ = name
        self.ID = ID
        self._labrad_name = labrad_name
        self._server = server
        self._cxn = server._cxn
        self._prot = self._cxn._cxn
        self._mgr = server._mgr
        self._num_listeners = 0

    def refresh(self):
        return self._refresh()

    @inlineCallbacks
    def _refresh(self):
        info = yield self._mgr.getSettingInfo(self._server.ID, self.ID)
        self.__doc__, self.accepts, self.returns, self.notes = info

    def __call__(self, *args, **kw):
        """Send a request to this setting."""
        tag = extractKey(kw, 'tag', None) or self.accepts
        if len(args) == 0:
            args = None
        elif len(args) == 1:
            args = args[0]
        resp = self._server._send([(self.ID, args, tag)], **kw)
        resp.addCallback(lambda resp: resp[0][1])
        return resp
    
    @inlineCallbacks
    def connect(self, handler, context=(0, 0),
                connectargs=(), connectkw={},
                handlerargs=(), handlerkw={}):
        """Connect a handler to messages from this signal.
        
        This is only applicable if the remote setting handles
        signal connection and disconnection.  We also keep
        track of the number of handlers that have been added to
        this setting.
        """
        self._prot.addListener(handler,
                               source=self._server.ID, context=context, ID=self.ID,
                               args=handlerargs, kw=handlerkw)
        self._num_listeners += 1
        try:
            yield self.__call__(self.ID, context=context, *connectargs, **connectkw)
        except:
            self._prot.removeListener(handler,
                                      source=self._server.ID, context=context, ID=self.ID)
            self._num_listeners -= 1
            raise
    
    def disconnect(self, handler, context=(0, 0),
                   disconnectargs=(), disconnectkw={}):
        """Disconnect a handler for messages from this signal.
        
        If the number of handlers drops to zero, we make a request to
        tell the signal to stop sending us messages.
        """
        self._prot.removeListener(handler, source=self._server.ID, context=context, ID=self.ID)
        self._num_listeners = max(self._num_listeners - 1, 0)
        return self.__call__(context=context, *disconnectargs, **disconnectkw)

class AsyncPacketWrapper(object):
    """Represents a LabRAD packet to a server."""
    
    def __init__(self, server, **kw):
        self.settings = MultiDict()
        self._server = server
        self._packet = []
        self._kw = kw

        for name in server.settings:
            s = server.settings[name]
            name, labrad_name, ID = s.name, s._labrad_name, s.ID
            wrapped = self._wrap(s)
            wrapped.name = name
            setattr(self, name, wrapped)
            self.settings[name, labrad_name, ID] = wrapped

    def send(self, **kw):
        """Send this packet to the server."""
        records = [rec[:3] for rec in self._packet]
        resp = self._server._send(records, **dict(self._kw, **kw))
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
        def wrapped(*args, **kw):
            key = extractKey(kw, 'key', None)
            tag = extractKey(kw, 'tag', None) or accepts
            if len(args) == 0:
                args = None
            elif len(args) == 1:
                args = args[0]
            self._packet.append((ID, args, tag, key))
            return self
        return wrapped

class AsyncServerWrapper:
    """Represents a remote LabRAD server."""
    
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

    _staticAttrs = ['settings', 'refresh', 'context', 'packet',
                    'sendMessage']
    
    def sendMessage(self, ID, *args, **kw):
        """Send a message to this server."""
        tag = extractKey(kw, 'tag', [])
        if len(args) == 0:
            args = None
        elif len(args) == 1:
            args = args[0]
        self._cxn._sendMessage(self.ID, [(ID, args, tag)], **kw)
    
    def _fixName(self, name):
        if name in self._staticAttrs:
            name = 'lr_' + name
        return name

    @inlineCallbacks
    def _addSetting(self, name, labrad_name, ID):
        try:
            setting = yield wrapAsync(
                self._settingWrapper, self, name, labrad_name, ID)
        except:
            pass
        else:
            self.settings[name, labrad_name, ID] = setting
            setattr(self, name, setting)

    @inlineCallbacks
    def _refreshSetting(self, name):
        setting = getattr(self, name)
        try:
            yield setting._refresh()
        except:
            yield self._delSetting(name)
        

    def _delSetting(self, name):
        if hasattr(self, name):
            delattr(self, name)
            del self.settings[name]
        return defer.succeed(None)

    _settingWrapper = AsyncSettingWrapper
    _packetWrapper = AsyncPacketWrapper

    def context(self):
        """Create a new context for talking to this server."""
        return self._cxn.context()

    def packet(self, **kw):
        """Create a new packet for this server."""
        return self._packetWrapper(self, **kw)

    def __call__(self):
        return self
        # TODO: this should make a clone that can have different
        # default keyword args, and, in particular, should talk
        # to the server in a different context

    def __getitem__(self, key):
        return self.settings[key]

    def _send(self, *args, **kw):
        """Send packet to this server."""
        return self._cxn._send(self.ID, *args, **kw)

@inlineCallbacks
def getConnection(host=C.MANAGER_HOST, port=C.MANAGER_PORT, name="Python Client", password=None):
    """Connect to LabRAD and return a deferred that fires the protocol object."""
    if password is None:
        password = protocol.getPassword()
    p = yield protocol.factory.connectTCP(host, port, C.TIMEOUT)
    yield p.loginClient(password, name)
    returnValue(p)

@inlineCallbacks
def connectAsync(host=C.MANAGER_HOST, port=C.MANAGER_PORT, name="Python Client", password=None):
    """Connect to LabRAD and return a deferred that fires the client object."""
    p = yield getConnection(host, port, name, password)
    cxn = IClientAsync(p)
    yield cxn.refresh()
    cxn.onDisconnect = p.onDisconnect
    returnValue(cxn)

def runAsync(func, *args, **kw):
    from twisted.internet import reactor
    @inlineCallbacks
    def runIt():
        try:
            yield func(*args, **kw)
        finally:
            reactor.stop()
    reactor.callWhenRunning(runIt)
    reactor.run()

class ClientAsync(object):
    """Adapt a LabRAD request protocol object to an asynchronous client."""
    
    implements(IClientAsync)
    
    def __init__(self, prot):
        self.servers = MultiDict()
        self._cxn = prot
        self._mgr = ILabradManager(self._cxn)
        self._next_context = 1
        
    _staticAttrs = ['servers', 'refresh', 'context']

    def refresh(self):
        """Refresh the cache of available servers and their settings."""
        return self._refresh()

    @inlineCallbacks
    def _refresh(self):
        """Update the cache of available LabRAD servers."""
        
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
        """Create a new communication context for this connection."""
        context = (0, self._next_context)
        self._next_context += 1
        return context

    def __getitem__(self, key):
        return self.servers[key]

    def _send(self, target, records, *args, **kw):
        """Send a packet over this connection."""
        return self._cxn.sendRequest(target, records, *args, **kw)
        
    def _sendMessage(self, target, records, *args, **kw):
        """Send a message over this connection."""
        return self._cxn.sendMessage(target, records, *args, **kw)
        
    def disconnect(self):
        self._cxn.disconnect()

registerAdapter(ClientAsync, ILabradProtocol, IClientAsync)

def wrapAsync(cls, *args, **kw):
    obj = cls(*args, **kw)
    d = obj._refresh()
    d.addCallback(lambda x: obj)
    return d


class PacketResponse(object):
    """Wrapper for response packets from LabRAD servers.

    Attributes are added to access the records in this
    response packet coming from each setting.  For each
    setting called by the packet, we add an attribute to
    the access the response from that setting.  If a setting
    is called more than once, all responses from that setting
    are collected into a list.  Responses can be accessed
    by name or ID, unless a key was specified for the call,
    in which case the response is accessible via the key only.
    """
    def __init__(self, resp, server, packet):
        self.settings = MultiDict()
        index = 0
        for (pID, pData, pAccepts, key), (ID, data) in zip(packet, resp):
            setting = server.settings[ID]
            name, labrad_name = setting.name, setting._labrad_name
            # if this record has a key, index by key only
            # otherwise by setting name, LabRAD name and ID
            if key is not None:
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

