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
labrad.client

Contains a blocking client connection to labrad.
"""

from labrad import constants as C, types as T, thread, protocol, util
from labrad.errors import Error
from labrad.interfaces import ILabradManager
from labrad.thread import blockingCallFromThread as block, DelayedResponse
from labrad.wrappers import PacketResponse, getConnection
from labrad.util import mangle, indent, MultiDict, PrettyDict, extractKey

from twisted.internet import reactor

import getpass

class NotFoundError(Error):
    code = 10
    def __init__(self, key):
        self.msg = 'Could not find "%s".' % key

class SettingWrapper(object):
    """Object to wrap a single setting on a single server.

    Information about the setting is loaded on demand and cached.
    You can force a refresh of this information by calling the refresh()
    method.  Calling this object directly will send a request.
    """
    def __init__(self, server, name, pyName, ID):
        self.name = self.__name__ = self._labrad_name = name
        self.ID = ID
        self._py_name = pyName
        self._server = server
        self._mgr = server._mgr
        self._refreshed = False
        self._num_listeners = 0

    def __call__(self, *args, **kw):
        wait = extractKey(kw, 'wait', True)
        wrap = extractKey(kw, 'wrap', True)
        tag = extractKey(kw, 'tag', None) or self.accepts
        if not len(args):
            args = None
        elif len(args) == 1:
            args = args[0]
        resp = DelayedResponse(self._server._send,
                               [(self.ID, args, tag)], **kw)
        if wrap:
            resp.addCallback(lambda resp: resp[0][1])
        return resp.wait() if wait else resp

    # data to be loaded on demand
    @property
    def accepts(self):
        self._refresh()
        return self._accepts

    @property
    def returns(self):
        self._refresh()
        return self._returns

    @property
    def description(self):
        self._refresh()
        return self.__doc__

    @property
    def notes(self):
        self._refresh()
        return self._notes

    def _refresh(self):
        if not self._refreshed:
            info = block(self._mgr.getSettingInfo, self._server.ID, self.ID)
            self.__doc__, self._accepts, self._returns, self._notes = info
            self._refreshed = True
        
    def refresh(self):
        # mark that we need to refresh.  This doesn't happen immediately,
        # but instead only when needed later due to property access
        self._refreshed = False

    def __repr__(self):
        return """\
LabRAD Setting: "%s" >> "%s" (ID=%d)

%s

Accepts:
%s

Returns:
%s

%s
""" % (self._server.name, self.name, self.ID, self.description,
       util.indent('\n'.join(self.accepts)),
       util.indent('\n'.join(self.returns)), self.notes)


class DynamicAttrDict(PrettyDict):
    _parent = None

    def __iter__(self):
        # copy the list of keys so we can add/remove during iteration
        return iter(list(self.keys()))
    
    def __getitem__(self, key):
        try:
            return super(DynamicAttrDict, self).__getitem__(key)
        except KeyError:
            # force refresh and try again
            if self._parent:
                self._parent.refresh(now=True)
            try:
                return super(DynamicAttrDict, self).__getitem__(key)
            except KeyError:
                raise NotFoundError(key)


class HasDynamicAttrs(object):
    """An object with attributes looked up dynamically on labrad."""
    def __init__(self):
        self.__attrs = None
        self.__cache = None
        self._refreshed = False

    @property
    def _attrs(self):
        if not self._refreshed:
            self._refresh()
        return self.__attrs

    def _fixName(self, name):
        pyName = mangle(name)
        if pyName in self._staticAttrs:
            pyName = 'lr_' + pyName
        return pyName

    def _refresh(self):
        """Update the list of available attributes."""
        try:
            if self._refreshed:
                return

            if self.__attrs is None:
                self.__attrs = DynamicAttrDict()
                self.__attrs._parent = self
                self.__cache = {}

            # get current list of attributes
            attrs = self._getAttrs()
            if len(attrs):
                names, IDs = zip(*attrs)
            else:
                names, IDs = [], []
            pyNames = [self._fixName(name) for name in names]
            attrs = zip(names, pyNames, IDs)

            # delete names of old attributes (but leave them in the cache)
            deletions = [pyName for pyName in self.__attrs if pyName not in pyNames]
            for pyName in deletions:
                del self.__attrs[pyName]

            # add new attributes
            additions = [(n, p, ID) for (n, p, ID) in attrs
                                    if p not in self.__attrs]
            for name, pyName, ID in additions:
                if name in self.__cache:
                    # pull from cache if possible, but
                    # tell attribute to refresh itself
                    s = self.__cache[name]
                    s.ID = ID # update attribute ID
                    if hasattr(s, 'refresh'):
                        s.refresh()
                else:
                    s = self._wrapAttr(self, name, pyName, ID)
                self.__cache[name] = s
                self.__attrs[pyName, name, ID] = s

            self._refreshed = True
        except Exception, e:
            print e, repr(e)

    def _getAttrs(self):
        """Get the current list of attributes from labrad.

        Should be overridden by subclasses with a method
        to get the attributes they need.
        """
        return []

    _staticAttrs = [] # static attributes names, so dynamic names don't collide
    _wrapAttr = lambda *a: None # should be overridden by subclasses

    def refresh(self, now=False):
        """Signal that a refresh is needed.

        If now is true, the refresh happens immediately,
        otherwise it is put off until actually needed later.
        """
        self._refreshed = False
        if now:
            self._refresh()

    def _getAttributeNames(self):
        """Return a list of dynamic attributes, for tab-completion"""
        self.refresh() # force refresh so the list is current
        return sorted(self._attrs.keys())

    def __getattr__(self, key):
        return self._attrs[key]

    def __getitem__(self, key):
        return self._attrs[key]


class ServerWrapper(HasDynamicAttrs):
    """A wrapper for a labrad server."""
    
    def __init__(self, cxn, name, pyName, ID):
        HasDynamicAttrs.__init__(self)
        self._cxn = cxn
        self.name = self._labrad_name = name
        self._py_name = pyName
        self.ID = ID

    @property
    def _mgr(self):
        return self._cxn._mgr

    _staticAttrs = ['settings', 'context', 'packet', 'sendMessage']
    _wrapAttr = SettingWrapper

    def _getAttrs(self):
        info = block(self._mgr.getServerInfo, self.ID)
        self.__doc__, self.notes, self._slist  = info
        return self._slist

    @property
    def settings(self):
        self._refresh()
        return self._attrs

    def context(self):
        return self._cxn.context()

    def packet(self, **kw):
        return PacketWrapper(self, **kw)

    def __call__(self, **kw):
        return self

    def _send(self, *args, **kw):
        return self._cxn._send(self.ID, *args, **kw)

    def sendMessage(self, ID, *args, **kw):
        """Send a message to this server."""
        tag = extractKey(kw, 'tag', [])
        if len(args) == 0:
            args = None
        elif len(args) == 1:
            args = args[0]
        self._cxn._sendMessage(self.ID, [(ID, args, tag)], **kw)

    def __repr__(self):
        return """\
LabRAD Server: %s (ID=%d)

%s

Settings:
%s

%s
""" % (self.name, self.ID, self.__doc__,
       indent(repr(self.settings)), self.notes)


class PacketWrapper(HasDynamicAttrs):
    """An object to encapsulate a labrad packet to a server."""

    def __init__(self, server, **kw):
        HasDynamicAttrs.__init__(self)
        self._server = server
        self._packet = []
        self._kw = kw

    def send(self, wait=True, **kw):
        """Send this packet to the server."""
        records = [rec[:3] for rec in self._packet]
        resp = DelayedResponse(self._server._send, records, **dict(self._kw, **kw))
        resp.addCallback(PacketResponse, self._server, self._packet)
        return resp.wait() if wait else resp

    @property
    def settings(self):
        self._refresh()
        return self._attrs

    _staticAttrs = ['settings', 'send']

    def _getAttrs(self):
        """Grab the list of the server's attributes."""
        ignored = self._server.settings # ensure refresh
        return self._server._slist

    def _wrapAttr(self, _parent, name, pyName, ID):
        s = self._server.settings[name]
        def wrapped(*args, **kw):
            key = extractKey(kw, 'key', None)
            tag = extractKey(kw, 'tag', None) or s.accepts
            if not len(args):
                args = None
            elif len(args) == 1:
                args = args[0]
            self._packet.append((s.ID, args, tag, key))
            return self
        return wrapped

    def __setitem__(self, key, value):
        """Update existing parts of the packet, indexed by key."""
        for i, (ID, data, accepts, rkey) in enumerate(self._packet):
            if key == rkey:
                self._packet[i] = ID, value, accepts, key

    def _recordRepr(self, ID, data, types, key):
        key_str = "" if key is None else " (key=%s)" % (key,)
        return "%s%s: %s" % (self._server.settings[ID].name, key_str, data)

    def __repr__(self):
        data_str = '\n'.join(self._recordRepr(*rec) for rec in self._packet)
        return """Packet for server: '%s'

Data:
%s
""" % (self._server.name, indent(data_str))


class Client(HasDynamicAttrs):
    def __init__(self, name):
        HasDynamicAttrs.__init__(self)
        self.name = name or 'Python Client (%s)' % util.getNodeName()
        self.connected = False
        self._next_context = 1

    def __enter__(self):
        """Enter the body of a with statement."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the body of a with statement."""
        try:
            self.disconnect()
        except:
            pass
        return False
        
    def _getAttrs(self):
        if not self.connected:
            return []
        return block(self._mgr.getServersList)

    _staticAttrs = ['servers', 'connect', 'disconnect', 'context']
    _wrapAttr = ServerWrapper

    @property
    def servers(self):
        self._refresh()
        return self._attrs

    def connect(self, host, port=C.MANAGER_PORT, timeout=C.TIMEOUT, password=None):
        thread.startReactor()
        name = 'Python Client (%s)' % util.getNodeName()
        self._cxn = block(getConnection, host, port, name, password)
        self._mgr = ILabradManager(self._cxn)
        self.ID = self._cxn.ID
        self.host, self.port = host, port
        self.connected = True

    def disconnect(self):
        if self.connected:
            def doDisconnect():
                self._factory.disconnect()
                return self._factory.onShutdown()
            block(self._cxn.disconnect)
            self.connected = False

    def context(self):
        context = 0, self._next_context
        self._next_context += 1
        return context

    def _send(self, target, records, *args, **kw):
        """Send a packet over this connection."""
        return self._cxn.sendRequest(target, records, *args, **kw)

    def _sendMessage(self, target, records, *args, **kw):
        """Send a message over this connection."""
        return block(self._cxn.sendMessage, target, records, *args, **kw)

    def __repr__(self):
        if self.connected:
            return """\
LabRAD Client: '%s' on %s:%s

Available servers:
%s
""" % (self.name, self.host, self.port, indent(repr(self.servers)))
        else:
            return """\
LabRAD Client: '%s'

Disconnected
""" % self.name
