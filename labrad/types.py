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
LabRAD <-> Python data conversion

All data in LabRAD packets is strictly typed, while python data
is dynamically typed.  But we can do a pretty good job converting
automatically back and forth between the two, and when we have
information about what types are allowed (for example when sending
to a server setting or returning from a setting when the accepted
and return types have been registered), we can do even better.
"""

from __future__ import absolute_import

import re
from struct import pack, unpack
import time
from types import InstanceType
from datetime import timedelta, datetime as dt
from itertools import chain, imap
from operator import itemgetter
import functools

from labrad import units as U
from labrad.units import Value, Complex

try:
    from numpy import ndarray, array, dtype, fromstring
    useNumpy = True
except ImportError:
    useNumpy = False

# helper classes

class Singleton(object):
    """Base class for singleton types.

    A singleton is a type with only one instance.  The first instance
    created gets stored in the class attribute _inst, and this same
    instance is returned thereafter.
    """
    def __new__(cls, *a, **kw):
        inst = getattr(cls, '_inst', None)
        if inst is None:
            inst = super(Singleton, cls).__new__(cls, *a, **kw)
            cls._inst = inst
        return inst

# a registry of parsing functions, keyed by type tag
_parsers = {}


class RegisterParser(type):
    """A metaclass for LabRAD types that have parsers.

    When each class is created, this function gets called and
    we register the __parse__ method of the class according
    to the tag that the class specifies.
    """
    def __new__(cls, name, bases, dict):
        c = type.__new__(cls, name, bases, dict)
        if 'tag' in dict:
            _parsers[dict['tag']] = c.__parse__
        return c


class Buffer(object):
    def __init__(self, s):
        if isinstance(s, Buffer):
            self.s = s.s
            self.ofs = s.ofs
        else:
            self.s = s
            self.ofs = 0

    def get(self, i=1):
        temp = self.s[self.ofs:self.ofs+i]
        self.ofs += i
        return temp
        
    def skip(self, i=1):
        self.ofs += i
    
    def __len__(self):
        return len(self.s) - self.ofs

    def __str__(self):
        return self.s[self.ofs:]
        
    def __getitem__(self, key):
        self.s = self.s[self.ofs:]
        self.ofs = 0
        return self.s[key]
        
    def strip(self, chars):
        self.s = self.s[self.ofs:].strip(chars)
        self.ofs = 0
        return self

    def index(self, char):
        return self.s.index(char, self.ofs)
        


# typetag parsing

def parseTypeTag(s):
    """Parse a type tag into a LabRAD type object."""
    try:
        if isinstance(s, LRType):
            return s
        s = Buffer(stripComments(s))
        ## this is a workaround for a bug in the manager
        if s[:1] == '_':
            return LRNone()
        types = []
        while len(s):
            types.append(parseSingleType(s))
        if len(types) == 0:
            return LRNone()
        elif len(types) == 1:
            return types[0]
        else:
            return LRCluster(*types)
    except Exception:
        print 'failed to parse:', s
        raise

WHITESPACE = ' ,\t'
        
def parseSingleType(s):
    """Parse a single type at the beginning of a type string."""
    s.strip(WHITESPACE)
    t = _parsers[s.get()](s)
    s.strip(WHITESPACE)
    return t

COMMENTS = re.compile('\{[^\{\}]*\}')
    
def stripComments(s):
    """Remove comments from a type tag.

    Inline comments are delimited by curly brackets {} and may not be nested.
    In addition, anything after a colon : is considered a comment.
    """
    return COMMENTS.sub('', s).split(':')[0]

def parseNumber(s):
    """Parse an integer at the beginning of a string."""
    s.strip(WHITESPACE)
    n = d = 0
    while len(s) and s[:1] in '0123456789':
        n = 10*n + int(s.get())
        d += 1
    if d == 0:
        n = None # no digits
    return n

def parseUnits(s):
    """Parse units from a typestring."""
    s = s.strip(WHITESPACE)
    if s[:1] != '[':
        return None
    length = s.index(']') + 1
    return s.get(length)[1:-1]


# a registry of types and type functions that can determine
# the LabRAD type of python data
_types = {}

def registerType(cls, t):
    """Register the LabRAD type for a python class.

    This is used in a case where the LabRAD type is known
    immediately from the python class.
    """
    classes = cls if isinstance(cls, tuple) else (cls,)
    t = parseTypeTag(t) if isinstance(t, str) else t
    for cls in classes:
        _types[cls] = t

_typeFuncs = {}

def registerTypeFunc(cls, typeFunc):
    """Register a LabRAD type function for a python class.

    The type function takes a python object of class cls and
    returns an appropriate LabRAD type object for it.
    """
    classes = cls if isinstance(cls, tuple) else (cls,)
    for cls in classes:
        _typeFuncs[cls] = typeFunc

def typeFunc(cls):
    """Decorator for registering type functions."""
    def register(func):
        registerTypeFunc(cls, func)
        return func
    return register

def getType(obj):
    """Get LabRAD type of python data."""
    if hasattr(obj, '__lrtype__'):
        return obj.__lrtype__()

    t = type(obj)
    # handle classic classes
    if t == InstanceType:
        t = obj.__class__

    # check if we know this type
    if t in _types:
        return _types[t]
    
    # check if we have a type function for this type
    if t in _typeFuncs:
        return _typeFuncs[t](obj)
    else:
        # check if we have a type function for a superclass
        for cls in _typeFuncs:
            if issubclass(t, cls):
                return _typeFuncs[cls](obj)
    raise TypeError("No LabRAD type for: %r." % obj)

def isType(obj, tag):
    return getType(obj) <= parseTypeTag(tag)


# flattening and unflattening

def unflatten(s, t, endianness='>'):
    """Unflatten labrad data into python data, given a prototype t.

    The prototype can be a labrad type tag or a prototype object
    created the parseTypeTag function.  At present, the default
    unflatteners are called at each stage, according to t.
    """
    if isinstance(t, str):
        t = parseTypeTag(t)
    if isinstance(s, str):
        s = Buffer(s)
    return t.__unflatten__(s, endianness)


# a registry of flattener functions that can convert python data
# into LabRAD data, keyed on the python class that they can accept

def flatten(obj, types=[], endianness='>'):
    """Flatten python data into labrad data.

    Flatten returns a tuple of (flattened string, type object).  The
    type object can be converted into a type tag by calling str(typeobj).

    A type or list of accepted types can be provided in the form of
    type tags (str) or type objects as created by parseTypeTag.  If
    accepted types are provided, flatten will produce data of the first
    compatible type, and will fail if none of the types are compatible.

    If not types are provided, we first check to see if the object has
    an __lrflatten__ method, in which case it will be called.  Then we
    check the registry of flattening functions, to see whether one exists
    for the object type, or a superclass.
    """
    if hasattr(obj, '__lrflatten__'):
        return obj.__lrflatten__(endianness)

    if not isinstance(types, list):
        types = [types]
    types = [parseTypeTag(t) for t in types]
    
    t = getType(obj)

    if not len(types):
        # if there are no type suggestions, just try to
        # flatten to the default type
        s = t.__flatten__(obj, endianness)
    else:
        # check the list of allowed types for one compatible
        # with the computed type
        foundCompatibleType = False
        for tt in types:
            if t <= tt:
                foundCompatibleType = True
                break
            elif tt <= t:
                t = tt
                foundCompatibleType = True
                break
        if foundCompatibleType:
            s = t.__flatten__(obj, endianness)
        else:
            # since we haven't found anything compatible,
            # just try to flatten to any of the suggested types
            s = None
            for t in types:
                try:
                    s = t.__flatten__(obj, endianness)
                except Exception:
                    pass
                else:
                    break
            if s is None:
                raise FlatteningError(obj, types)
    return s, t

def evalLRData(s):
    """Evaluate LR data in a namespace with all LRTypes."""
    return eval(s)

def reprLRData(s):
    """Make a repr of LR data in a namespace with all LRTypes."""
    return repr(s)

# LabRAD type classes

class LRType(object):
    """Base class of all LabRAD type objects.

    These type classes manage parsing and creation of type tags,
    provide default unflatteners, and also provide methods to test
    type equality and compatibility.
    """
    
    __metaclass__ = RegisterParser

    def __str__(self):
        """Convert to a type tag string format.

        All type object should return a LabRAD-compatible representation
        of themselves when __str__ is called, so that a type tag can
        be created from a type object simply by calling str(typeobj).
        """
        return self.tag

    def __repr__(self):
        """Convert to a verbose string representation.

        This string representation should be valid python code that could
        be evaluated to create the corresponding type object, assuming
        the names from the type module have been imported.
        """
        return self.__class__.__name__ + '()'

    @classmethod
    def __parse__(cls, s):
        """Parse type tag into appropriate python type objects.

        The parse function takes the remaining string (after the
        tag for this type has been removed).  The function may need
        to consume some more of the string to determine the type.  It
        should return a tuple of (type object, rest of string).
        """
        return cls()

    @classmethod
    def __lrtype__(cls, obj):
        return cls()

    def __eq__(self, other):
        """Test whether this type is equal to another.

        By default, we just check whether the types are the same.
        """
        return type(self) == type(other)

    def __le__(self, other):
        """Test whether this type is equal to on more specific than another.

        By default, just check for equality.
        """
        return type(self) == type(other) or type(other) == LRAny

    def isFullySpecified(self):
        return True

    isFixedWidth = True
    width = 0
        
    def __width__(self, s, endianness):
        s.skip(self.width)
        return self.width
        
    def __unflatten__(self, s, endianness):
        """Unflatten data from a string representation.

        Each LabRAD type object implements a default unflattener that
        creates python data from the LabRAD data string.  The unflattener
        returns a tuple of (python object, rest of string).
        """
        raise NotImplementedError

    def __flatten__(self, data, endianness):
        """Flatten python data to this LabRAD type.

        Each LabRAD type object implements a default unflattener that
        creates python data from the LabRAD data string.  The unflattener
        returns a tuple of (flattened string, labrad type).  Note that
        other unflattener functions can be registered later to override
        this default behavior and unflatten to different python types.
        """
        raise NotImplementedError


class LRAny(LRType, Singleton):
    """A placeholder for any single LabRAD type."""
    tag = '?'

    def isFullySpecified(self):
        return False


class LRNone(LRType, Singleton):
    """An empty piece of LabRAD data."""
    tag = '_'
    
    def __unflatten__(self, s, endianness):
        return None
    
    def __flatten__(self, data, endianness):
        if data is not None:
            raise FlatteningError(data, self)
        return ''

registerType(type(None), LRNone())


class LRBool(LRType, Singleton):
    """A simple boolean."""
    tag = 'b'
    width = 1
    
    def __unflatten__(self, s, endianness):
        return bool(ord(s.get(1)))
    
    def __flatten__(self, b, endianness):
        if not isinstance(b, bool):
            raise FlatteningError(b, self)
        return chr(b)

registerType(bool, LRBool())


class LRInt(LRType, Singleton):
    """A signed 32-bit integer."""
    tag = 'i'
    width = 4
    def __unflatten__(self, s, endianness):
        return unpack(endianness + 'i', s.get(4))[0]
    
    def __flatten__(self, n, endianness):
        if not isinstance(n, (int, long)):
            raise FlatteningError(n, self)
        return pack(endianness + 'i', n)

registerType(int, LRInt())


class LRWord(LRType, Singleton):
    """An unsigned 32-bit integer."""
    tag = 'w'
    width = 4
    def __unflatten__(self, s, endianness):
        return long(unpack(endianness + 'I', s.get(4))[0])
    
    def __flatten__(self, n, endianness):
        if not isinstance(n, (int, long)):
            raise FlatteningError(n, self)
        return pack(endianness + 'I', n)

registerType(long, LRWord())


class LRStr(LRType, Singleton):
    """A string of bytes prefixed by a 32-bit length field."""
    tag = 's'
    isFixedWidth = False
    
    def __width__(self, s, endianness):
        width = unpack(endianness + 'i', s.get(4))[0]
        s.skip(width)
        return 4 + width
    
    def __unflatten__(self, s, endianness):
        n = unpack(endianness + 'i', s.get(4))[0]
        return s.get(n)
    
    def __flatten__(self, s, endianness):
        if not isinstance(s, str):
            raise FlatteningError(s, self)
        return pack(endianness + 'I', len(s)) + s

registerType(str, LRStr())


def timeOffset():
    now = time.time()
    return (dt(1904, 1, 1) - dt.utcfromtimestamp(now)
                           + dt.fromtimestamp(now))

class LRTime(LRType, Singleton):
    """A timestamp in LabRAD format.

    Timestamp format comes from LabVIEW, and consists of two
    64-bit integers, representing seconds and fractions of a
    second since Jan. 1, 1904, UTC.
    """

    tag = 't'
    width = 16
    
    def __unflatten__(self, s, endianness):
        secs, us = unpack(endianness + 'QQ', s.get(16))
        us = float(us)/pow(2,64)*pow(10,6)
        t = timeOffset() + timedelta(seconds=secs, microseconds=us)
        return t

    def __flatten__(self, t, endianness):
        diff = t - timeOffset()
        secs = diff.days * (60 * 60 * 24) + diff.seconds
        us = long(float(diff.microseconds)/pow(10,6)*pow(2,64))
        return pack(endianness + 'QQ', secs, us)

registerType(dt, LRTime())


class LRValue(LRType):
    """Represents the type of a real number that carries units."""
    
    tag = 'v'
    width = 8

    def __init__(self, unit=None):
        self.unit = unit

    def __str__(self):
        if self.unit is None:
            return self.tag
        else:
            return self.tag + '[%s]' % self.unit

    def __repr__(self):
        return self.__class__.__name__ + '(%r)' % self.unit

    @classmethod
    def __parse__(cls, s):
        return cls(parseUnits(s))

    def __eq__(self, other):
        return type(self) == type(other) and self.unit == other.unit
    
    def __le__(self, other):
        # this method is a bit funky.  The <= relationship determines
        # which types are allowed to be coerced in flattening.  If the
        # other type is also a value, we allow this if we have a unit,
        # or the other value does not.  In other words, the only case
        # disallowed is the case where we have no unit but the other
        # type does.  This prevents the unit from getting lost in the coercion.
        if type(other) == LRAny:
            return True
        if type(self) != type(other):
            return False
        if other.unit is None:
            return True
        if self.unit is None:
            return False
        return True

    def isFullySpecified(self):
        return self.unit is not None

    def __unflatten__(self, s, endianness):
        v = unpack(endianness + 'd', s.get(8))[0]
        if self.unit is not None:
            v = Value(v, self.unit)
        return v
        
    @classmethod
    def __lrtype__(cls, v):
        if isinstance(v, U.WithUnit):
            return cls(v.unit)
        return cls(U.Unit(''))
        
    def __flatten__(self, v, endianness):
        v = self.__check_units__(v)
        return pack(endianness + 'd', float(v))
        
    def __check_units__(self, v):
        # TODO: implement full labrad unit conversion semantics in pylabrad
        # If we're trying to flatten to unitless value, then v must be float
        # or Value with units either None or ''
        if not isinstance(v, U.WithUnit):
            # v is a float or complex; only accept if out unit is None or ''
            if self.unit not in [None, '']:
                raise FlatteningError(v, self)
        else:
            # v has units; convert to desired units
            v = v[self.unit]
        return v

registerTypeFunc((float, Value), LRValue.__lrtype__)


class LRComplex(LRValue):
    """Represents the type of a complex number that carries units."""
    
    tag = 'c'
    width = 16
    
    def __unflatten__(self, s, endianness):
        real, imag = unpack(endianness + 'dd', s.get(16))
        c = complex(real, imag)
        if self.unit is not None:
            c = Complex(c, self.unit)
        return c
    
    def __flatten__(self, c, endianness):
        c = self.__check_units__(c)
        c = complex(c)
        return pack(endianness + 'dd', c.real, c.imag)

registerTypeFunc((complex, Complex), LRComplex.__lrtype__)


class LRCluster(LRType):
    """A cluster type for bundling pieces of data together."""
    
    tag = '('

    def __init__(self, *items):
        self.items = items
        
    def __str__(self):
        return '(%s)' % ''.join(str(i) for i in self.items)

    def __repr__(self):
        contents = '(%s)' % ', '.join(repr(i) for i in self.items)
        return self.__class__.__name__ + contents

    @classmethod
    def __parse__(cls, s):
        items = []
        while len(s) and s[0] != ')':
            items.append(parseSingleType(s))
        if s.get(1) != ')':
            raise Exception('Unbalanced parentheses in cluster.')
        return cls(*items)

    @classmethod
    def __lrtype__(cls, c):
        return cls(*[getType(i) for i in c])

    def __len__(self):
        return len(self.items)

    def __getitem__(self, key):
        return self.items[key]

    def __le__(self, other):
        """Test whether this type is more specific than another.

        Compatibility requires that both clusters have the same length,
        and all of our items are more specific than the corresponding
        items in the other cluster.
        """
        return (type(other) == LRAny or
                (type(self) == type(other) and
                 len(self.items) == len(other.items) and
                 all(s <= o for s, o in zip(self.items, other.items))))

    def isFullySpecified(self):
        return all(t.isFullySpecified() for t in self.items)
    
    @property
    def isFixedWidth(self):
        if hasattr(self, '_isFixedWidth'):
            return self._isFixedWidth
        self._isFixedWidth = all(item.isFixedWidth for item in self.items)
        if self._isFixedWidth:
            self.width = sum(item.width for item in self.items)    
    
    def __width__(self, s, endianness):
        return sum(item.__width__(s, endianness) for item in self.items)
        
    def __unflatten__(self, s, endianness):
        """Unflatten items into a python tuple."""
        return tuple(unflatten(s, t, endianness) for t in self.items)

    def __flatten__(self, c, endianness):
        """Flatten python tuple to LabRAD cluster."""
        if len(c) == 0:
            raise FlatteningError('Cannot flatten zero-length clusters')
        if len(c) != len(self.items):
            raise FlatteningError('Cannot flatten %s to %s' % (c, self.items))
        if LRAny() in self.items:
            strs = []
            items = []
            for t, elem in zip(self.items, c):
                if t == LRAny():
                    s, t = flatten(elem, endianness=endianness)
                    strs.append(s)
                    items.append(t)
                else:
                    s = t.__flatten__(elem, endianness)
                    strs.append(s)
                    items.append(t)
            self.items = items # warning: type mutated here
            return ''.join(strs)
        return ''.join(t.__flatten__(elem, endianness) for t, elem in zip(self.items, c))

registerTypeFunc(tuple, LRCluster.__lrtype__)


#class LRChoice(LRType):
#    """Represents a choice among different data types."""
#    
#    tag = '<'
#
#    def __init__(self, *choices):
#        self.choices = choices
#        
#    def __str__(self):
#        return '<%s>' % '|'.join(str(i) for i in self.choices)
#
#    def __repr__(self):
#        contents = '<%s>' % '|'.join(repr(i) for i in self.choices)
#        return self.__class__.__name__ + contents
#
#    @classmethod
#    def __parse__(cls, s):
#        choices = []
#        while len(s) and s[0] != '>':
#            cluster = []
#            while len(s) and s[0] != '|':
#                cluster.append(parseSingleType(s))
#            if len(cluster) == 0:
#                raise Exception('Type choices cannot be empty')
#            elif len(cluster) == 1:
#                choices.append(cluster[0])
#            else:
#                choices.append(LRCluster(*choices))
#            if s.get(1) != '|': # pop off the '|'
#                raise Exception('Expected "|" to delimit type choices.')
#        if s.get(1) != '>':
#            raise Exception('Unbalanced brackets in choice.')
#        return cls(*choices)
#
#    #@classmethod
#    #def __lrtype__(cls, c):
#    #    return cls(*[getType(i) for i in c])
#
#    def __len__(self):
#        return len(self.choices)
#
#    def __getitem__(self, key):
#        return self.choices[key]
#
#    def __le__(self, other):
#        """Test whether this type is more specific than another.
#
#        Compatibility requires that both clusters have the same length,
#        and all of our items are more specific than the corresponding
#        items in the other cluster.
#        """
#        # FIXME: implement this
#        return (type(other) == LRAny or
#                all(s <= other for s in self.choices))
#
#    def isFullySpecified(self):
#        return len(self.choices) == 1
#    
#    @property
#    def isFixedWidth(self):
#        return False
#        #if hasattr(self, '_isFixedWidth'):
#        #    return self._isFixedWidth
#        #self._isFixedWidth = all(item.isFixedWidth for item in self.items)
#        #if self._isFixedWidth:
#        #    self.width = sum(item.width for item in self.items)    
#    
#    def __width__(self, s, endianness):
#        return sum(item.__width__(s, endianness) for item in self.items)
#        
#    def __unflatten__(self, s, endianness):
#        """Unflatten items into a python tuple."""
#        return tuple(unflatten(s, t, endianness) for t in self.items)
#
#    def __flatten__(self, c, endianness):
#        """Flatten python tuple to LabRAD cluster."""
#        if len(c) == 0:
#            raise FlatteningError('Cannot flatten zero-length clusters')
#        if len(c) != len(self.items):
#            raise FlatteningError('Cannot flatten %s to %s' % (c, self.items))
#        if LRAny() in self.items:
#            strs = []
#            items = []
#            for t, elem in zip(self.items, c):
#                if t == LRAny():
#                    s, t = flatten(elem, endianness=endianness)
#                    strs.append(s)
#                    items.append(t)
#                else:
#                    s = t.__flatten__(elem, endianness)
#                    strs.append(s)
#                    items.append(t)
#            self.items = items # warning: type mutated here
#            return ''.join(strs)
#        return ''.join(t.__flatten__(elem, endianness) for t, elem in zip(self.items, c))


class LRList(LRType):
    """A multidimensional rectangular array type."""
    
    tag = '*'

    def __init__(self, elem=None, depth=1):
        self.elem = elem
        self.depth = depth

    def __str__(self):
        depth = str(self.depth) if self.depth > 1 else ''
        elem = str(self.elem) if self.elem is not None else '_'
        return '*%s%s' % (depth, elem)

    def __repr__(self):
        contents = '(%r, depth=%r)' % (self.elem, self.depth)
        return self.__class__.__name__ + contents

    isFixedWidth = False
    
    def __width__(self, s, endianness):
        n, elem = self.depth, self.elem
        dims = unpack(endianness + ('i'*n), s.get(4*n))
        size = reduce(lambda x, y: x*y, dims)
        if elem is None:
            width = 0
        elif elem.isFixedWidth:
            width = size * elem.width
        else:
            newBuf = Buffer(s)
            width = sum(elem.__width__(newBuf, endianness) for _ in xrange(size))
        s.skip(width)
        return 4*n + width
        
    @classmethod
    def __parse__(cls, s):
        s = s.strip(WHITESPACE)
        # get the list dimensionality
        n = parseNumber(s)
        if n == 0:
            raise Exception('Cannot create 0-dimensional list.')
        n = n or 1 # if there were no digits, make a 1D list
        s = s.strip(WHITESPACE)
        if s[:1] == '_':
            t = None # empty list
            s.get() # drop underscore
        else:
            t = parseSingleType(s)
        return cls(t, n)

    @classmethod
    def __lrtype__(cls, L):
        depth, temp = 1, L
        while len(temp) and isinstance(temp[0], list):
            depth, temp = depth+1, temp[0]

        def iterND(ls):
            if len(ls) and isinstance(ls[0], list):
                return chain(*(iterND(i) for i in ls))
            else:
                return iter(ls)

        t = LRAny()
        size = 0
        for elem in iterND(L):
            size += 1
            elem_t = getType(elem)
            if elem_t <= t:
                t = elem_t
            if t.isFullySpecified():
                break
        if size == 0:
            t = LRNone()
        return cls(t, depth)

    @classmethod
    def __lrtype_array__(cls, L):
        #numpy.dtype overloads the == operator, and 'in'
        #uses ==, so our use of in here should be ok
        if L.dtype == 'bool': t = LRBool()
        elif L.dtype in ['>i4', '<i4']: t = LRInt()
        elif L.dtype in ['>u4', '<u4']: t = LRWord()
        elif L.dtype in ['>u8', '<u8']: t = LRWord()
        elif L.dtype in ['>f8', '<f8']: t = LRValue()
        elif L.dtype in ['>c16', '<c16']: t = LRComplex()
        else:
            raise Exception("Can't flatten array of %s" % L.dtype)
        return cls(t, depth=len(L.shape))
        
    def __le__(self, other):
        """Test whether this type is more specific than another.

        We check the list dimensionality (depth) and the element type.
        """
        return (type(other) == LRAny or
                (type(self) == type(other) and
                 self.depth == other.depth and
                 (other.elem is None or self.elem <= other.elem)))

    def __eq__(self, other):
        """Test whether this type is equal to another.

        We check the list dimensionality (depth) and the element type.
        """
        return (type(self) == type(other) and
                self.depth == other.depth and
                self.elem == other.elem)

    def isFullySpecified(self):
        return self.elem.isFullySpecified()

    def __unflatten__(self, s, endianness):
        data = s.get(self.__width__(Buffer(s), endianness))
        return LazyList(data, self, endianness)
    
        """Unflatten to nested python list."""
        # get list dimensions
        n = self.depth
        dims = unpack(endianness + ('i'*n), s.get(4*n))
        size = reduce(lambda x, y: x*y, dims)
        if self.elem is None or size == 0:
            return nestedList([], n-1)
        def unflattenNDlist(s, dims):
            if len(dims) == 1:
                return [unflatten(s, self.elem, endianness) for _ in xrange(dims[0])]
            else:
                return [unflattenNDlist(s, dims[1:]) for _ in xrange(dims[0])]
        return unflattenNDlist(s, dims)
        
    def __flatten__(self, L, endianness):
        """Flatten (nested) python list to LabRAD list.

        Lists must be homogeneous and rectangular.
        """
        if hasattr(L, 'aslist') and not hasattr(L, '_list'):
            # if we get a LazyList that hasn't been unflattened,
            # we can just return the original data unchanged
            # if  it has been unflattened, though, then it may
            # have been changed since lists are mutable, so we
            # can't take this shortcut
            return L._data
        if useNumpy and isinstance(L, ndarray):
            return self.__flatten_array__(L, endianness)
        if self.elem == LRAny():
            self.elem = self.__lrtype__(L).elem
        lengths = [None] * self.depth
        def flattenNDlist(ls, n=0):
            if lengths[n] is None:
                lengths[n] = len(ls)
            if len(ls) != lengths[n]:
                raise Exception('List is not rectangular.')
            if n+1 == self.depth:
                return ''.join(self.elem.__flatten__(e, endianness) for e in ls)
            else:
                return ''.join(flattenNDlist(row, n+1) for row in ls)
        flat = flattenNDlist(L)
        lengths = [l or 0 for l in lengths]
        return pack(endianness + ('i' * len(lengths)), *lengths) + flat
        
    def __flatten_array__(self, a, endianness):
        """Flatten numpy array to LabRAD list."""
        shape = a.shape[:self.depth]
        if len(shape) != self.depth:
            raise Exception("Bad array shape.")
        dims = pack(endianness + ('i' * len(shape)), *shape)
        if self.elem == LRAny():
            self.elem = self.__lrtype_array__(a).elem
        
        # determine what dtype we would like to have
        wanted_dtype = _known_dtypes.get(type(self.elem), None)
        
        if wanted_dtype is not None:
            if wanted_dtype == 'u4':
                if a.dtype in ['<i8', '>i8']:
                    a = a.astype(endianness + 'u4')
            if a.dtype.itemsize > dtype(wanted_dtype).itemsize:
                raise Exception("Narrowing type cast while flattening numpy array: dtype=%s, wanted_dtype=%s" % (a.dtype, dtype(wanted_dtype)))
            a = a.astype(endianness + wanted_dtype)
        else:
            elems = imap(itemgetter(0), (flatten(i, endianness=endianness) for i in a.flat))
            return dims + ''.join(elems)
        return dims + a.tostring()
        
_known_dtypes = {
    LRBool: 'u1',
    LRInt: 'i4',
    LRWord: 'u4',
    LRValue: 'f8',
    LRComplex: 'c16'
}

registerTypeFunc(list, LRList.__lrtype__)
if useNumpy:
    registerTypeFunc(ndarray, LRList.__lrtype_array__)


def nestedList(obj, n):
    for _ in range(n):
        obj = [obj]
    return obj
    

class LRError(LRType):
    """LabRAD error type."""

    tag = 'E'

    def __init__(self, payload=LRNone()):
        self.payload = payload

    def __str__(self):
        if self.payload is LRNone():
            return self.tag
        else:
            return self.tag + str(self.payload)

    def __repr__(self):
        return self.__class__.__name__ + '(%r)' % self.payload

    @classmethod
    def __parse__(cls, s):
        payload = parseSingleType(s)
        return LRError(payload)

    def __eq__(self, other):
        return type(self) == type(other) and self.payload == other.payload

    def __le__(self, other):
        return type(self) == type(other) and self.payload <= other.payload

    def isFullySpecified(self):
        return self.payload.isFullySpecified()

    def __lrtype__(self, E):
        payload = getattr(E, 'payload', None)
        return LRError(getType(payload))

    isFixedWidth = False
    
    def __width__(self, s, endianness):
        s.skip(4)
        return 4 + LRStr().__width__(s, endianness) + self.payload.__width__(s, endianness)
        
    def __unflatten__(self, s, endianness):
        """Unflatten to Error type to capture code, message and payload."""
        if self.payload is LRNone():
            t = LRCluster(LRInt(), LRStr())
            code, msg = unflatten(s, t, endianness)
            payload = None
        else:
            t = LRCluster(LRInt(), LRStr(), self.payload)
            code, msg, payload = unflatten(s, t, endianness)
        return Error(msg, code, payload)

    def __flatten__(self, E, endianness):
        """Flatten python Exception to LabRAD error."""
        # TODO add ability to grab tracebacks here, or more information of other types
        code = getattr(E, 'code', 0)
        msg = getattr(E, 'msg', repr(E))
        payload = getattr(E, 'payload', None)
        t = LRCluster(LRInt(), LRStr(), self.payload)
        s, t = flatten((int(code), str(msg), payload), t, endianness)
        self.payload = t.items[2]
        return s

registerTypeFunc(Exception, LRError().__lrtype__)


# data types

class Error(Exception):
    """LabRAD base error class.

    Captures the error code and message of a LabRAD error, as well
    as any payload sent along with it.
    """

    # TODO register error classes by code, so remote errors can be reraised

    msg = ''
    payload = None
    
    def __init__(self, msg=None, code=0, payload=None):
        self.msg = str(msg or self.__doc__)
        self.code = int(code)
        self.payload = payload

    def __str__(self):
        return '(%d) %s [payload=%r]' % (self.code, self.msg, self.payload)

    def __repr__(self):
        return 'Error(code=%r, msg=%r, payload=%r)' % (self.code, self.msg, self.payload)

    def __lrtype__(self):
        return LRError(getType(self.payload))

    def __lrflatten__(self, endianness):
        s, t = flatten((self.code, self.msg, self.payload), endianness=endianness)
        return s, LRError(t.items[2])

class Int(int):
    def __lrtype__(self):
        return LRInt()

class Word(int):
    def __lrtype__(self):
        return LRWord()


class LazyList(list):
    """A proxy object for LabRAD lists.
    
    LazyList will be unflattened as needed when list methods are called,
    or can alternately be unflattened as a numpy array, bypassing the slow
    step of creating a large python list.
    """
    def __init__(self, data, tag, endianness):
        self._data = data
        self._lrtype = parseTypeTag(tag)
        self._unflattened = False
        self._endianness = endianness
    
    def __lrtype__(self):
        return self._lrtype
    
    @property
    def elem(self):
        return self._lrtype.elem

    @property
    def aslist(self):
        self._unflattenList()
        return list(self)

    @property
    def astuple(self):
        return tuple(self.aslist)
        
    @property
    def asarray(self):
        self._unflattenArray()
        return self._array
    
    def _unflattenList(self):
        """Unflatten to nested python list."""
        if self._unflattened:
            return

        self._unflattened = True
            
        s = Buffer(self._data)
        n, elem = self._lrtype.depth, self._lrtype.elem
        dims = unpack(self._endianness + ('i'*n), s.get(4*n))
        size = reduce(lambda x, y: x*y, dims)
        
        if elem is None or size == 0:
            self.extend(nestedList([], n-1))
        else:
            def unflattenND(dims):
                if len(dims) == 1:
                    return [unflatten(s, elem, self._endianness) for _ in xrange(dims[0])]
                else:
                    return [unflattenND(dims[1:]) for _ in xrange(dims[0])]
            self.extend(unflattenND(dims))
        self._list = True
       
    def _unflattenArray(self):
        """Unflatten to numpy array."""
        if hasattr(self, '_array'):
            return self._array
        if hasattr(self, '_list'):
            self._array = array(list(self))
            return self._array
        
        s = Buffer(self._data)
        n, elem = self._lrtype.depth, self._lrtype.elem
        dims = unpack(self._endianness + ('i'*n), s.get(4*n))
        size = reduce(lambda x, y: x*y, dims)
        
        make = lambda t, width: fromstring(s.get(size*width), dtype=dtype(t))
        if elem == LRBool(): a = make(self._endianness + 'u1', 1)
        elif elem == LRInt(): a = make(self._endianness + 'i4', 4)
        elif elem == LRWord(): a = make(self._endianness + 'u4', 4)
        elif elem <= LRValue(): a = make(self._endianness + 'f8', 8)
        elif elem <= LRComplex(): a = make(self._endianness + 'c16', 16)
        else:
            a = array([unflatten(s, elem, self._endianness) for _ in xrange(size)])
        a.shape = dims + a.shape[1:] # handle clusters as elements
        self._array = a
        return self._array


# attributes of the LazyList class will be wrapped so
# that when called, the LazyList will be unflattened
_listAttrs = [
    '__add__', '__contains__', '__delitem__', '__delslice__', '__eq__', '__ge__',
    '__getitem__', '__getslice__', '__gt__', '__iadd__', '__imul__',
    '__iter__', '__le__', '__len__', '__lt__', '__mul__', '__ne__', '__repr__',
    '__reversed__', '__rmul__', '__setitem__', '__setslice__', '__str__',
    'append', 'count', 'extend', 'index', 'insert', 'pop', 'remove',
    'reverse', 'sort']

def _wrap(attr):
    func = getattr(list, attr)
    @functools.wraps(func, assigned=['__name__', '__doc__'])
    def wrapped(self, *args, **kw):
        self._unflattenList()
        return func(self, *args, **kw)
    return wrapped

for attr in _listAttrs:
    setattr(LazyList, attr, _wrap(attr))

# errors

class FlatteningError(Error):
    """Raised when data cannot be flattened into a valid labrad type."""

    code = 12345
    
    def __init__(self, data, types=None):
        if types:
            if isinstance(types, list):
                types = [str(t) for t in types]
            else:
                types = str(types)
            self.msg = 'Could not flatten %r to %s.' % (data, types)
        else:
            self.msg = 'Could not flatten %r.' % (data,)
