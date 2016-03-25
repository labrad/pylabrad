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

import warnings

from labrad import constants as C, types as T
from labrad.backend import ManagerService
from labrad.concurrent import map_future, MutableFuture
from labrad.errors import Error
from labrad.support import (mangle, indent, PrettyMultiDict, FlatPacket,
                            PacketRecord, PacketResponse, hexdump)

class NotFoundError(Error):
    code = 10
    def __init__(self, key):
        self.msg = 'Could not find "%s".' % key

def unwrap(s, after='|'):
    def trim(line):
        return line.split(after, 1)[-1]
    return '\n'.join(trim(line) for line in s.split('\n'))

class SettingWrapper(object):
    """Object to wrap a single setting on a single server.

    Information about the setting is loaded on demand and cached.
    You can force a refresh of this information by calling the refresh()
    method. Calling this object directly will send a request and block until
    the result is available. Calling the .future method will send a request and
    return a future with which to get the result later.

    The keyword argument unflatten=False will suppress the normal unflattening
    and return a FlatData object.
    """
    def __init__(self, server, name, pyName, ID):
        self.name = self.__name__ = self._labrad_name = name
        self.ID = ID
        self._py_name = pyName
        self._server = server
        self._mgr = server._mgr
        self._refreshed = False

    def __call__(self, *args, **kw):
        wait = kw.pop('wait', True)
        if not wait:
            warnings.warn("Calling settings with wait=False is deprecated. "
                          "Use setting.future(...) instead.")
        f = self.future(*args, **kw)
        return f.result() if wait else f

    def future(self, *args, **kw):
        wrap = kw.pop('wrap', True)
        tag = kw.pop('tag', None) or self.accepts
        if not len(args):
            args = None
        elif len(args) == 1:
            args = args[0]
        flat = T.flatten(args, tag)
        f = self._server._send([(self.ID, flat)], **kw)
        if wrap:
            f = map_future(f, lambda resp: resp[0][1])
        return MutableFuture(f)

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
            info = self._mgr.getSettingInfoByName(self._server.ID, self.name)
            self.__doc__, self._accepts, self._returns, self._notes, self.ID = info
            self._refreshed = True

    def refresh(self):
        # mark that we need to refresh.  This doesn't happen immediately,
        # but instead only when needed later due to property access
        self._refreshed = False

    def __repr__(self):
        return unwrap("""\
            |LabRAD Setting: "%s" >> "%s" (ID=%d)
            |
            |%s
            |
            |Accepts:
            |%s
            |
            |Returns:
            |%s
            |
            |%s """) % (self._server.name, self.name, self.ID, self.description,
                        indent('\n'.join(self.accepts)),
                        indent('\n'.join(self.returns)), self.notes)


class DynamicAttrDict(PrettyMultiDict):
    _parent = None

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
                    # pull from cache if possible
                    s = self.__cache[name]
                    s.ID = ID # update attribute ID
                else:
                    s = self._wrapAttr(self, name, pyName, ID)
                self.__cache[name] = s
                self.__attrs[pyName, name, ID] = s

            # refresh all attributes
            for attr in self.__attrs.values():
                if hasattr(attr, 'refresh'):
                    attr.refresh()

            self._refreshed = True
        except Exception, e:
            print 'Error refreshing dynamic attributes:'
            print e, repr(e)

    def _getAttrs(self):
        """Get the current list of attributes from labrad.

        Should be overridden by subclasses with a method
        to get the attributes they need.
        """
        return []

    _staticAttrs = [] # static attributes names, so dynamic names don't collide

    def _wrapAttr(self, *args):
        """Should be overridden by subclasses"""

    def refresh(self, now=False):
        """Signal that a refresh is needed.

        If now is true, the refresh happens immediately,
        otherwise it is put off until actually needed later.
        """
        self._refreshed = False
        if now:
            self._refresh()

    def __dir__(self):
        """Return a list of attributes for tab-completion.
        """
        self.refresh() # force refresh so the list is current
        return sorted(set(self._attrs.keys() + self.__dict__.keys() + dir(type(self))))
    
    def __getattr__(self, key):
        return self._attrs[key]

    def __getitem__(self, key):
        return self._attrs[key]


class ServerWrapper(HasDynamicAttrs):
    """A wrapper for a labrad server."""

    def __init__(self, cxn, name, pyName, ID, context=None):
        HasDynamicAttrs.__init__(self)
        self._cxn = cxn
        self._mgr = cxn._mgr
        self.name = self._labrad_name = name
        self._py_name = pyName
        self.ID = ID
        self._ctx = context

    _staticAttrs = ['settings', 'context', 'packet', 'sendMessage']
    _wrapAttr = SettingWrapper

    def _getAttrs(self):
        info = self._mgr.getServerInfo(self.ID)
        doc, notes, self._slist = info
        self.__doc__ = doc + '\n' + notes
        return self._slist

    @property
    def settings(self):
        self._refresh()
        return self._attrs

    def context(self):
        return self._cxn.context()

    def packet(self, **kw):
        return PacketWrapper(self, **kw)

    def __call__(self, context=None):
        """Create a new server wrapper based on this one but with a new default context."""
        if context is None:
            context = self._cxn.context()
        return ServerWrapper(self._cxn, self.name, self._py_name, self.ID, context=context)

    def _send(self, *args, **kw):
        if 'context' not in kw or kw['context'] is None:
            kw['context'] = self._ctx
        return self._cxn._send(self.ID, *args, **kw)

    def sendMessage(self, ID, *args, **kw):
        """Send a message to this server."""
        if 'context' not in kw or kw['context'] is None:
            kw['context'] = self._ctx
        tag = kw.pop('tag', [])
        if len(args) == 0:
            args = None
        elif len(args) == 1:
            args = args[0]
        self._cxn._sendMessage(self.ID, [(ID, args, tag)], **kw)

    def __repr__(self):
        self._refresh()
        return unwrap("""\
            |LabRAD Server: %s (ID=%d)
            |
            |%s
            |
            |Settings:
            |%s""") % (self.name, self.ID, self.__doc__,
                       indent(repr(self.settings)))


class PacketWrapper(HasDynamicAttrs):
    """An object to encapsulate a labrad packet to a server."""

    def __init__(self, server, **kw):
        HasDynamicAttrs.__init__(self)
        self._server = server
        self._packet = []
        self._kw = kw

    def send(self, wait=True, **kw):
        """Send this packet to the server and wait for the result.

        Using the keyword argument unflatten=False will suppress the
        default unflattening and return FlatData objects"""
        if not wait:
            warnings.warn("Sending packets with wait=False is deprecated. "
                          "Use packet.send_future(...) instead.")
        f = self.send_future(**kw)
        f.result()
        return f.result() if wait else f

    def send_future(self, **kw):
        """Send this packet to the server and get the result as a future."""
        records = [(rec.ID, rec.flat) for rec in self._packet]
        f = self._server._send(records, **dict(self._kw, **kw))
        f = map_future(f, PacketResponse, self._server, self._packet)
        return MutableFuture(f)

    @property
    def settings(self):
        self._refresh()
        return self._attrs

    def to_cluster(self, context=None):
        """Get a representation of this packet as a flattenable cluster.

        This method returns a representation of this packet as a cluster of
        (context, name, records), where records is itself a cluster of
        (setting name, value), one for each setting record in the packet.
        """
        if context is None:
            context = self._kw.get('context', self._server._ctx)
            if context is None:
                context = (self._server._cxn.ID, 0)
        records = tuple((rec.name, rec.flat) for rec in self._packet)
        return FlatPacket(context, self._server.name, records)

    _staticAttrs = ['settings', 'send', 'send_future', 'to_cluster']

    def _getAttrs(self):
        """Grab the list of the server's attributes."""
        self._server._refresh() # ensure refresh
        return self._server._slist

    def _wrapAttr(self, _parent, name, pyName, ID):
        s = self._server.settings[name]
        def wrapped(*args, **kw):
            key = kw.pop('key', None)
            tag = kw.pop('tag', None) or s.accepts
            if not len(args):
                args = None
            elif len(args) == 1:
                args = args[0]
            flat = T.flatten(args, tag)
            rec = PacketRecord(ID=s.ID, data=args, tag=tag, flat=flat, key=key,
                               name=name)
            self._packet.append(rec)
            return self
        return wrapped

    def __setitem__(self, key, value):
        """Update existing parts of the packet, indexed by key."""
        for i, rec in enumerate(self._packet):
            if key == rec.key:
                flat = T.flatten(value, rec.tag)
                self._packet[i] = rec._replace(data=value, flat=flat)

    def _dataStr(self, data):
        if len(data) < 160:
            return self._dataRepr(data)
        else:
            x = self._dataRepr(data[0:32])
            '\n'.join('    ' + y for y in x.splitlines())
            return "string of length %d beginning with... \n%s" % (len(data), x)

    def _dataRepr(self, data):
        if all((ord(x) > 31 and ord(x) < 127) or x.isspace() for x in data): # Is string printable ascii
            return data
        else:
            return hexdump(data)

    def _recordRepr(self, rec, short=False):
        """Create a string representation of a packet record.

        Includes the setting name and result key (if specified), as well as
        a possibly truncated repr of the data for this setting.
        """
        key_str = "" if rec.key is None else " (key=%s)" % (rec.key,)
        prefix = '%s%s: ' % (rec.name, key_str)
        data_str = self._dataStr(str(rec.data)) if short else self._dataRepr(str(rec.data))
        data_str = data_str.replace('\n', '\n' + ' '*len(prefix))
        return prefix + data_str

    def __str__(self):
        return self.__repr__(True)

    def __repr__(self, short=False):
        """Create a string representation of this packet.

        Includes the server the packet is intended for, as well as all the
        records that have been added to the packet.
        """
        data_str = '\n'.join(self._recordRepr(rec, short=short) for rec in self._packet)
        return unwrap("""\
            |Packet for server: '%s'
            |
            |Data:
            |%s""") % (self._server.name, indent(data_str))


class Client(HasDynamicAttrs):
    def __init__(self, cxn, context=None):
        HasDynamicAttrs.__init__(self)
        self._backend = cxn
        self._mgr = ManagerService(cxn)
        if context is None:
            context = cxn.context()
        self._ctx = context

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

    def __call__(self, context=None):
        return Client(self._backend, context)

    def _getAttrs(self):
        if not self.connected:
            return []
        return self._mgr.getServersList()

    _staticAttrs = ['servers', 'connect', 'disconnect', 'context', 'spawn']
    _wrapAttr = ServerWrapper

    @property
    def servers(self):
        self._refresh()
        return self._attrs

    # attributes proxied to the underlying connection, which may be shared among multiple clients
    @property
    def name(self):
        return self._backend.name

    @property
    def ID(self):
        return self._backend.ID

    @property
    def host(self):
        return self._backend.host

    @property
    def port(self):
        return self._backend.port

    @property
    def connected(self):
        return self._backend.connected

    def connect(self, host, port=None, timeout=C.TIMEOUT, password=None,
                tls_mode=C.MANAGER_TLS):
        self._backend.connect(host, port=port, timeout=timeout,
                              password=password, tls_mode=tls_mode)

    def disconnect(self):
        self._backend.disconnect()

    def context(self):
        return self._backend.context()

    def spawn(self):
        """Start a new independent connection to the same manager."""
        return Client(self._backend.spawn())

    def _send(self, target, records, *args, **kw):
        """Send a packet over this connection."""
        if 'context' not in kw or kw['context'] is None:
            kw['context'] = self._ctx
        return self._backend.sendRequest(target, records, *args, **kw)

    def _sendMessage(self, target, records, *args, **kw):
        """Send a message over this connection."""
        if 'context' not in kw or kw['context'] is None:
            kw['context'] = self._ctx
        return self._backend.sendMessage(target, records, *args, **kw)

    def __repr__(self):
        if self.connected:
            return unwrap("""\
                |LabRAD Client: '%s' on %s:%s
                |
                |Available servers:
                |%s""") % (self.name, self.host, self.port,
                           indent(repr(self.servers)))
        else:
            return unwrap("""\
                |LabRAD Client: '%s'
                |
                |Disconnected""") % self.name


