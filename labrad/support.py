"""A collection of miscellaneous support functions and classes.

Most of these used to be located in labrad.util but have been moved here
to break the explicit dependency on twisted.
"""

import collections
import getpass
import os
import socket
import keyword

from labrad import constants

def getNodeName():
    return os.environ.get('LABRADNODE', socket.gethostname().lower())


# cache of passwords, keyed by host name and port number
_password_cache = {}


def get_password(host=None, port=None, prompt=True):
    """Get a password from the environment, cache, or command line prompt.

    To add a password to the cache, use the cache_password function.

    Args:
        host (str or None): The manager host we want to connect to.
        port (int or None): The manager port we want to connect to.
        prompt (bool): Whether to prompt the user to enter a password at the
            command line if none is found in the cache or environment vars.

    Returns:
        (str or None): The password for the given host and port. If we did not
        find a password in the cache or environment vars and prompt was False,
        will return None.
    """
    # create cache entries for the environment password if needed
    if not _password_cache and constants.PASSWORD is not None:
        cache_password(host=constants.MANAGER_HOST,
                       port=constants.MANAGER_PORT,
                       password=constants.PASSWORD)
        cache_password(host=constants.MANAGER_HOST,
                       port=constants.MANAGER_PORT_TLS,
                       password=constants.PASSWORD)

    if host is None:
        host = constants.MANAGER_HOST
    if port is None:
        port = constants.MANAGER_PORT
    addr = (host, port)
    if addr in _password_cache:
        pw = _password_cache[addr]
    elif prompt:
        msg = 'Enter LabRAD password ({}:{}): '.format(host, port)
        pw = getpass.getpass(msg)
    else:
        pw = None
    return pw


def cache_password(host, port, password):
    """Add a password to the cache, for the given host and port.

    Cached passwords will be used for subsequent labrad connections to the same
    host and port. See the get_password function.

    Args:
        host (str): The manager host for this password.
        port (int): The manager port for this password.
        password (str): The password to cache.
    """
    _password_cache[host, port] = password


ALLOWED = 'abcdefghijklmnopqrstuvwxyz1234567890_'
FIRST = 'abcdefghijklmnopqrstuvwxyz_'

def mangle(name):
    """Return a modified string that is usable as a method name."""
    newname = ''.join(c if c in ALLOWED else '_' for c in name.lower())
    if newname[0] not in FIRST:
        newname = '_' + newname
    if newname in keyword.kwlist:
        newname = newname + '_'
    return newname

def indent(s, level=1):
    spc = ' ' * (4 * level)
    return '\n'.join(spc + line for line in s.split('\n'))

def extractKey(d, key, default):
    if key not in d:
        return default
    val = d[key]
    del d[key]
    return val

def chunks(s, size):
    '''
    Break a sequence into subsequences of at most size.
    '''
    for i in range(0, len(s), size):
        yield s[i:i+size]

def hexdump(s):
    '''
    Hex dump representation of string.  Each line containes 16 bytes represented
    first as hex codes with printable characters rendered on the right.
    '''
    result = []
    for substr in chunks(s, 16):
        hex_repr = " ".join('%02X' % (ord(x),) for x in substr)
        string_repr = "".join(x if ord(x) > 32 and ord(x) < 127 else '.' for x in substr)
        result.append('%s    %s' % (hex_repr.ljust(47), string_repr))
    return '\n'.join(result)


class SafeIterDict(dict):
    """A dict subclass that allows insertion and deletion while iterating.

    This is accomplished by overriding keys, items, values, etc. to return
    copies of their respective lists, rather than the lists themselves.
    Note that this negates the efficiency gains of using the iter* methods.
    """
    keys = lambda self: list(dict.keys(self))
    items = lambda self: list(dict.items(self))
    values = lambda self: list(dict.values(self))
    iterkeys = lambda self: iter(self.keys())
    iteritems = lambda self: iter(self.items())
    itervalues = lambda self: iter(self.values())
    __iter__ = lambda self: iter(self.keys())

class MultiDict(SafeIterDict):
    """Dictionary with multiple keys to the same value."""
    def __init__(self, *a, **kw):
        dict.__init__(self, *a, **kw)
        self.aliases = {} # mapping from aliases to keys
        self._keys = {} # mapping from keys to aliases

    def __repr__(self):
        items = []
        for k, v in self.iteritems():
            key_str = repr(k)
            if k in self._keys:
                aliases = [key_str] + [repr(a) for a in self._keys[k]]
                key_str = ' or '.join(aliases)
            items.append('%s: %r' % (key_str, v))
        return '{' + ', '.join(items) + '}'

    def __setitem__(self, k, v):
        if isinstance(k, tuple):
            k, aliases = k[0], k[1:]
            for alias in aliases:
                self.aliases[alias] = k
            self._keys[k] = aliases
        dict.__setitem__(self, k, v)

    def __delitem__(self, k):
        if k in self.aliases:
            k = self.aliases[k]
        # delete aliases for this key
        if k in self._keys:
            aliases = self._keys[k]
            for a in aliases:
                # only delete alias if it still points to this key
                if self.aliases[a] == k:
                    del self.aliases[a]
            del self._keys[k]
        dict.__delitem__(self, k)

    def __contains__(self, k):
        if k in self.aliases:
            k = self.aliases[k]
        return dict.__contains__(self, k)

    def __getitem__(self, k):
        if k in self.aliases:
            k = self.aliases[k]
        return dict.__getitem__(self, k)

    def _updateAliases(self, k, *aliases):
        """Update the aliases for a given key."""
        for a in set(self._keys[k]) - set(aliases):
            # remove old aliases, but only if they still
            # point to this key
            if self.aliases[a] == k:
                del self.aliases[a]
        for a in aliases:
            self.aliases[a] = k
        self._keys[k] = aliases

class PrettyMultiDict(MultiDict):
    def __repr__(self):
        return '\n'.join(sorted(self.keys()))


PacketRecord = collections.namedtuple('PacketRecord', ['ID', 'data', 'tag',
                                                       'flat', 'key', 'name'])


FlatPacket = collections.namedtuple('FlatPacket', ['context', 'name',
                                                   'records'])


class PacketResponse(object):
    """Wrapper for response packets from LabRAD servers.

    Attributes are added to access the records in this
    response packet coming from each setting.  For each
    setting called by the packet, we add an attribute to
    access the response from that setting.  If a setting
    is called more than once, all responses from that setting
    are collected into a list.  Responses can be accessed
    by name or ID, unless a key was specified for the call,
    in which case the response is accessible via the key only.
    """
    def __init__(self, resp, server, packet):
        # collect all responses from each setting or key
        temp = collections.defaultdict(list)
        for rec, (ID, data) in zip(packet, resp):
            key = rec.key
            setting = server.settings[ID]
            name, pyName = setting.name, setting._py_name
            # if this record has a key, index by key only
            # otherwise by setting name, python name and ID
            if key is not None:
                name = pyName = ID = key
            keys = (name, pyName, ID)
            temp[keys].append(data)
        # add data for the various settings
        self.settings = MultiDict()
        for (name, pyName, ID), l in temp.items():
            if len(l) == 1:
                l = l[0]
            if isinstance(pyName, str):
                setattr(self, pyName, l)
            self.settings[name, pyName, ID] = l

    def __getitem__(self, key):
        return self.settings[key]
