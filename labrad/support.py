"""A collection of miscellaneous support functions and classes.

Most of these used to be located in labrad.util but have been moved here
to break the explicit dependency on twisted.
"""

from collections import defaultdict
import getpass
import os
import socket

from labrad import constants

def getNodeName():
    return os.environ.get('LABRADNODE', socket.gethostname().lower())

def getPassword():
    """Get a password, either from the environment, or the command line."""
    if constants.PASSWORD is not None:
        pw = constants.PASSWORD
    else:
        pw = getpass.getpass('Enter LabRAD password: ')
    return pw

ALLOWED = 'abcdefghijklmnopqrstuvwxyz1234567890_'
FIRST = 'abcdefghijklmnopqrstuvwxyz_'

def mangle(name):
    """Return a modified string that is usable as a method name."""
    newname = ''.join(c if c in ALLOWED else '_' for c in name.lower())
    if newname[0] not in FIRST:
        newname = '_' + newname
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
        temp = defaultdict(list)
        for rec, (ID, data) in zip(packet, resp):
            key = rec[3]
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
