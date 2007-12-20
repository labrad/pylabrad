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
from datetime import timedelta, datetime

from labrad import constants as C, units as U
from labrad.units import Value, Complex

try:
    from numpy import ndarray, array, dtype, fromstring
    useNumpy = True
except:
    useNumpy = False
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
    def __init__(cls, name, bases, dict):
        super(RegisterParser, cls).__init__(cls, name, bases, dict)
        if 'tag' in dict:
            _parsers[dict['tag']] = cls.__parse__


class Buffer(object):
    def __init__(self, s):
        self.s = s

    def get(self, i):
        temp, self.s = self.s[:i], self.s[i:]
        return temp

    def __len__(self):
        return len(self.s)

    def __str__(self):
        return self.s
        

# typetag parsing

WHITESPACE = ' ,\t'
COMMENTS = re.compile('\{[^\{\}]*\}')

def parseTypeTag(s):
    """Parse a type tag into a LabRAD type object."""
    try:
        if isinstance(s, LRType):
            return s
        s = stripComments(s)
        ## TODO: this is a hack.  get rid of it.
        if s == '_':
            return LRNone()
        types = []
        while len(s):
            t, s = parseSingleType(s)
            types.append(t)
        if len(types) == 0:
            return LRNone()
        elif len(types) == 1:
            return types[0]
        else:
            return LRCluster(*types)
    except:
        print 'failed to parse:', s
        raise

def parseSingleType(s):
    """Parse a single type at the beginning of a type string."""
    s = s.strip(WHITESPACE)
    t, s = _parsers[s[:1]](s[1:])
    s = s.strip(WHITESPACE)
    return t, s

def stripComments(s):
    """Remove comments from a type tag.

    Inline comments are delimited by curly brackets {} and may not be nested.
    In addition, anything after a colon : is considered a comment.
    """
    s = re.sub(COMMENTS, '', s)
    # TODO: ignore colon inside unit strings
    s = s.split(':')[0]
    return s

def parseNumber(s):
    """Parse an integer at the beginning of a string."""
    s = s.strip(WHITESPACE)
    n = d = 0
    while s and s[:1] in '0123456789':
        n, s = 10*n + int(s[:1]), s[1:]
        d += 1
    if d == 0:
        n = None # no digits
    return n, s

def parseUnits(s):
    """Parse units from a typestring."""
    s = s.strip(WHITESPACE)
    if s[:1] != '[':
        return None, s
    close = s.index(']')
    units, s = s[1:close], s[close+1:]
    return units, s


# a registry of types and type functions that can determine
# the LabRAD type of python data
_types = {}

def registerType(cls, t):
    """Register the LabRAD type for a python class.

    This is used in a case where the LabRAD type is known
    immediately from the python class.
    """
    _types[cls] = t

_typeFuncs = {}

def registerTypeFunc(cls, typeFunc):
    """Register a LabRAD type function for a python class.

    The type function takes a python object of class cls and
    returns an appropriate LabRAD type object for it.
    """
    _typeFuncs[cls] = typeFunc

def typeFunc(cls):
    """Decorator for registering type functions."""
    def register(func):
        _typeFuncs[cls] = func
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
        # check if we have a flattener for a superclass
        for cls in _typeFuncs:
            if issubclass(t, cls):
                return _typeFuncs[cls](obj)
    raise TypeError("No LabRAD type for: %r." % obj)


# flattening and unflattening

def unflatten(s, t):
    """Unflatten labrad data into python data, given a prototype t.

    The prototype can be a labrad type tag or a prototype object
    created the parseTypeTag function.  At present, the default
    unflatteners are called at each stage, according to t.
    """
    if isinstance(t, str):
        t = parseTypeTag(t)
    if isinstance(s, str):
        s = Buffer(s)
    return t.__unflatten__(s)


# a registry of flattener functions that can convert python data
# into LabRAD data, keyed on the python class that they can accept
_flatteners = {}

def registerFlattener(cls, flatten):
    """Register a LabRAD flattener for a python type.

    The flatten function should take a python object of type cls
    and return a tuple of (flattened data string, type object).
    The type object must be a valid LRType object, such as those
    created by the parseTypeTag function.
    """
    _flatteners[cls] = flatten

def flattener(cls):
    """Decorator for registering flattener functions.

    A flattener should be a function that takes a python object of
    type cls and returns a tuple (flattened data str, labrad type),
    where labrad type is either a type tag (str) or an LRType object.
    """
    def register(func):
        _flatteners[cls] = func
        return func
    return register

def flatten(obj, types=[]):
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
        return obj.__lrflatten__()

    if not isinstance(types, list):
        types = [types]
    types = [parseTypeTag(t) for t in types]
    
    t = getType(obj)

    if not len(types):
        # if there are no type suggestions, just try to
        # flatten to the default type
        s = t.__flatten__(obj)
    else:
        # check the list of allowed types for one compatible
        # with the default type
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
            s = t.__flatten__(obj)
        else:
            # since we haven't found anything compatible,
            # just try to flatten to any of the suggested types
            s = None
            for t in types:
                try:
                    s = t.__flatten__(obj)
                except:
                    pass
                else:
                    break
            if s is None:
                raise FlatteningError(obj, types)
    return s, t

def evalLRData(s):
    """Evaluate LR data in a namespace with all LRTypes."""
    return eval(s)


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

        All type object should return a LabRAD-complient representation
        of themselves when __str__ is called, so that a type tag can
        be created from a type object simply by calling str(typeobj).
        """
        return self.tag

    def __repr__(self):
        """Conver to a verbose string representation.

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
        return cls(), s

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

    def __unflatten__(self, s):
        """Unflatten data from a string representation.

        Each LabRAD type object implements a default unflattener that
        creates python data from the LabRAD data string.  The unflattener
        returns a tuple of (python object, rest of string).
        """
        raise NotImplementedError

    def __flatten__(self, data):
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
    tag = ''
    def __unflatten__(self, s):
        return None
    
    def __flatten__(self, data):
        if data is not None:
            raise FlatteningError(data, self)
        return ''

registerType(type(None), LRNone())

class LRBool(LRType, Singleton):
    """A simple boolean."""
    tag = 'b'
    def __unflatten__(self, s):
        return bool(ord(s.get(1)))
    
    def __flatten__(self, b):
        if not isinstance(b, bool):
            raise FlatteningError(b, self)
        return chr(b)

registerType(bool, LRBool())


class LRInt(LRType, Singleton):
    """A signed 32-bit integer."""
    tag = 'i'
    def __unflatten__(self, s):
        return unpack('i', s.get(4))[0]
    
    def __flatten__(self, n):
        if not isinstance(n, (int, long)):
            raise FlatteningError(n, self)
        return pack('i', n)

registerType(int, LRInt())


class LRWord(LRType, Singleton):
    """An unsigned 32-bit integer."""
    tag = 'w'
    def __unflatten__(self, s):
        return long(unpack('I', s.get(4))[0])
    
    def __flatten__(self, n):
        if not isinstance(n, (int, long)):
            raise FlatteningError(n, self)
        return pack('I', n)

registerType(long, LRWord())


class LRStr(LRType, Singleton):
    """A string of bytes prefixed by a 32-bit length field."""
    tag = 's'
    def __unflatten__(self, s):
        n = unpack('i', s.get(4))[0]
        return s.get(n)
    
    def __flatten__(self, s):
        if not isinstance(s, str):
            raise FlatteningError(s, self)
        return pack('I', len(s)) + s

registerType(str, LRStr())


def timeOffset():
    now = time.time()
    return datetime(1904,1,1) - datetime.utcfromtimestamp(now) \
                              + datetime.fromtimestamp(now)

class LRTime(LRType, Singleton):
    """A timestamp in LabRAD format.

    Timestamp format comes from LabVIEW, and consists of two
    64-bit integers, representing seconds and fractions of a
    second since Jan. 1, 1904, UTC.
    """

    tag = 't'
    
    def __unflatten__(self, s):
        secs, us = unpack('QQ', s.get(16))
        us = float(us)/pow(2,64)*pow(10,6)
        t = timeOffset() + timedelta(seconds=secs, microseconds=us)
        return t

    def __flatten__(self, t):
        diff = t - timeOffset()
        secs = diff.days * (60 * 60 * 24) + diff.seconds
        us = long(float(diff.microseconds)/pow(10,6)*pow(2,64))
        return pack('QQ', secs, us)

registerType(datetime, LRTime())


class LRValue(LRType):
    """Represents the type of a real number that carries units."""
    
    tag = 'v'

    def __init__(self, units=None):
        self.units = units

    def __str__(self):
        if self.units is None:
            return self.tag
        else:
            return self.tag + '[%s]' % self.units

    def __repr__(self):
        return self.__class__.__name__ + '(%r)' % self.units

    @property
    def parsedUnit(self):
        if not hasattr(self, '_parsedUnit'):
            if self.units == None:
                self._parsedUnit = None
            else:
                self._parsedUnit = U._findUnit(self.units)
        return self._parsedUnit

    @classmethod
    def __parse__(cls, s):
        units, s = parseUnits(s)
        return cls(units), s

    def __eq__(self, other):
        return type(self) == type(other) and self.units == other.units
    
    def __le__(self, other):
        return type(other) == LRAny or \
               (type(self) == type(other) and \
                (self.units == other.units or other.units is None))

    def isFullySpecified(self):
        return self.units is not None

    def __unflatten__(self, s):
        v = unpack('d', s.get(8))[0]
        if self.parsedUnit is not None:
            v = Value(v, self.parsedUnit)
        return v

    def __flatten__(self, v):
        if isinstance(v, Value):
            v = v[self.parsedUnit]
        return pack('d', float(v))

registerType(float, LRValue())

@typeFunc(Value)
def getValueType(pq):
    return LRValue(pq.unit.labradName())


class LRComplex(LRValue):
    """Represents the type of a complex number that carries units."""
    
    tag = 'c'
    
    def __unflatten__(self, s):
        real, imag = unpack('dd', s.get(16))
        return Complex(complex(real, imag), self.parsedUnit)

    def __flatten__(self, c):
        if isinstance(c, Complex):
            c = c[self.parsedUnit]
        c = complex(c)
        return pack('dd', c.real, c.imag)

registerType(complex, LRComplex())

@typeFunc(Complex)
def getValueType(pq):
    return LRComplex(pq.unit.labradName())


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
        while len(s) and s[:1] != ')':
            t, s = parseSingleType(s)
            items.append(t)
        if s[:1] != ')':
            raise Exception('Unbalanced parentheses in cluster.')
        return cls(*items), s[1:]

    @classmethod
    def __lrtype__(cls, c):
        items = [getType(i) for i in c]
        return cls(*items)

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
        return type(other) == LRAny or \
               (type(self) == type(other) and \
                len(self.items) == len(other.items) and \
                all(s <= o for s, o in zip(self.items, other.items)))

    def isFullySpecified(self):
        return all(t.isFullySpecified() for t in self.items)

    def __unflatten__(self, s):
        """Unflatten items into a python tuple."""
        return tuple(unflatten(s, t) for t in self.items)

    def __flatten__(self, c):
        """Flatten python tuple to LabRAD cluster."""
        if len(c) == 0:
            raise FlatteningError('Cannot flatten zero-length clusters')
        return ''.join(t.__flatten__(elem) for t, elem in zip(self.items, c))

registerTypeFunc(tuple, LRCluster.__lrtype__)


class LRList(LRType):
    """A multidimensional rectangular array type."""
    
    tag = '*'

    def __init__(self, elem=None, depth=1):
        self.elem = elem
        self.depth = depth

        # use numpy arrays for numeric element types
        if useNumpy and elem in [LRBool(), LRInt(), LRWord()]:
            self.__unflatten__ = self.__unflatten_array__

    def __str__(self):
        depth = '' if self.depth == 1 else str(self.depth)
        elem = '_' if self.elem is None else str(self.elem)
        return '*%s%s' % (depth, elem)

    def __repr__(self):
        contents = '(%r, depth=%r)' % (self.elem, self.depth)
        return self.__class__.__name__ + contents

    @classmethod
    def __parse__(cls, s):
        s = s.strip(WHITESPACE)
        # get the list dimensionality
        n, s = parseNumber(s)
        if n == 0:
            raise Exception('Cannot create 0-dimensional list.')
        n = n or 1 # if there were no digits, make a 1D list
        s = s.strip(WHITESPACE)
        if s[:1] == '_':
            # empty list
            return cls(None, n), s[1:]
        else:
            t, s = parseSingleType(s)
            return cls(t, n), s

    @classmethod
    def __lrtype__(cls, L):
        depth, temp = 1, L
        while len(temp) and isinstance(temp[0], list):
            depth, temp = depth+1, temp[0]

        def iterND(ls):
            if isinstance(ls, list):
                for i in ls:
                    for e in iterND(i):
                        yield e
            else:
                yield ls

        t = LRAny()
        for elem in iterND(L):
            elem_t = getType(elem)
            if elem_t <= t:
                t = elem_t
            if t.isFullySpecified():
                break
        return cls(t, depth)

    def __le__(self, other):
        """Test whether this type is more specific than another.

        We check the list dimensionality (depth) and the element type.
        """
        return type(other) == LRAny or \
               (type(self) == type(other) and \
                self.depth == other.depth and \
                (other.elem is None or self.elem <= other.elem))

    def __eq__(self, other):
        """Test whether this type is equal to another.

        We check the list dimensionality (depth) and the element type.
        """
        return type(self) == type(other) and \
               self.depth == other.depth and \
               self.elem == other.elem

    def isFullySpecified(self):
        return self.elem.isFullySpecified()

    def __unflatten__(self, s):
        """Unflatten to nested python list."""
        # get list dimensions
        n = self.depth
        dims = unpack('i'*n, s.get(4*n))
        size = reduce(lambda x, y: x*y, dims)
        if self.elem is None or size == 0:
            return nestedList([], n-1)
        def unflattenNDlist(s, dims):
            if len(dims) == 1:
                return [unflatten(s, self.elem) for _ in xrange(dims[0])]
            else:
                return [unflattenNDlist(s, dims[1:]) for _ in xrange(dims[0])]
        return unflattenNDlist(s, dims)

    def __unflatten_array__(self, s):
        """Unflatten to numpy array."""
        # get list dimensions
        n = self.depth
        dims = unpack('i'*n, s.get(4*n))
        size = reduce(lambda x, y: x*y, dims)
        if self.elem is None or size == 0:
            a = array([])
            a.shape = (0,) * n
            return a
        if self.elem == LRBool():
            t = dtype('bool')
            L = size * 1
        elif self.elem == LRInt():
            t = dtype('int32')
            L = size * 4
        elif self.elem == LRWord():
            t = dtype('uint32')
            L = size * 4
        else:
            a = array([unflatten(s, self.elem) for _ in xrange(size)])
            a.shape = dims
            return a
        a = fromstring(s.get(L), dtype=t)
        a.shape = dims
        return a

    def __flatten__(self, L):
        """Flatten (nested) python list to LabRAD list.

        Lists must be homogeneous and rectangular.
        """
        lengths = [None] * self.depth
        def flattenNDlist(ls, n=0):
            if lengths[n] is None:
                lengths[n] = len(ls)
            if len(ls) != lengths[n]:
                raise Exception('List is not rectangular.')
            if n+1 == self.depth:
                return ''.join(self.elem.__flatten__(e) for e in ls)
            else:
                return ''.join(flattenNDlist(row, n+1) for row in ls)
        flat = flattenNDlist(L)
        lengths = [l or 0 for l in lengths]
        return pack('i' * len(lengths), *lengths) + flat

registerTypeFunc(list, LRList.__lrtype__)


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
        payload, s = parseSingleType(s)
        return LRError(payload), s

    def __eq__(self, other):
        return type(self) == type(other) and self.payload == other.payload

    def __le__(self, other):
        return type(self) == type(other) and self.payload <= other.payload

    def isFullySpecified(self):
        return self.payload.isFullySpecified()

    def __lrtype__(self, E):
        payload = getattr(E, 'payload', None)
        return LRError(getType(payload))

    def __unflatten__(self, s):
        """Unflatten to Error type to capture code, message and payload."""
        if self.payload is LRNone():
            code, msg = unflatten(s, LRCluster(LRInt(), LRStr()))
            payload = None
        else:
            code, msg, payload = \
                unflatten(s, LRCluster(LRInt(), LRStr(), self.payload))
        return Error(msg, code, payload)

    def __flatten__(self, E):
        """Flatten python Exception to LabRAD error."""
        code = getattr(E, 'code', 0)
        msg = getattr(E, 'msg', repr(E))
        payload = getattr(E, 'payload', None)
        t = LRCluster(LRInt(), LRStr(), self.payload)
        s, t = flatten((int(code), str(msg), payload), t)
        self.payload = t.items[2]
        return s

registerTypeFunc(Exception, LRError().__lrtype__)


# data types

class Error(Exception):
    """LabRAD base error class.

    Captures the error code and message of a LabRAD error, as well
    as any payload sent along with it.
    """

    # TODO: register error classes by code, so remote errors can be reraised

    msg = ''
    payload = None
    
    def __init__(self, msg=None, code=0, payload=None):
        self.msg = str(msg or self.__doc__)
        self.code = int(code)
        self.payload = payload

    def __str__(self):
        return '(%d) %s [payload=%r]' % (self.code, self.msg, self.payload)

    def __repr__(self):
        return 'Error(%r, %r, %r)' % (self.code, self.msg, self.payload)

    def __lrtype__(self):
        return LRError(getType(self.payload))

    def __lrflatten__(self):
        s, t = flatten((self.code, self.msg, self.payload))
        return s, LRError(t.items[2])
    

# python flatteners

@flattener(Exception)
def flattenException(E):
    """Flatten generic python Exceptions to LabRAD errors."""
    code = getattr(E, 'code', 0)
    msg = getattr(E, 'msg', repr(E))
    payload = getattr(E, 'payload', None)
    s, t = flatten((int(code), str(msg), payload))
    return s, LRError(t.items[2])


@flattener(tuple)
def flattenTuple(c):
    """Flatten python tuple to LabRAD cluster."""
    items, types = zip(*[flatten(i) for i in c])
    return ''.join(items), LRCluster(*types)


@flattener(list)
def flattenList(L):
    """Flatten (nested) python list to LabRAD list.

    Lists must be homogeneous and rectangular.
    """
    # TODO: make list flattening recursive
    n = 1
    temp = L
    while len(temp) and isinstance(temp[0], list):
        n += 1
        temp = temp[0]
    def flattenNDlist(ls):
        if not len(ls):
            items, types, lengths = [''], [None], [[]]
        elif isinstance(ls[0], list):
            items, types, lengths = \
                zip(*[flattenNDlist(row) for row in ls])
        else:
            items, types = zip(*[flatten(i) for i in ls])
            lengths = [[]]
        base_t = types[0]
        for t in types:
            if t <= base_t:
                base_t = t
            elif base_t <= t:
                pass
            else:
                raise Exception('Inhomogeneous list.')
        for length in lengths:
            if length != lengths[0]:
                raise Exception('List is not rectangular.')
        return ''.join(items), base_t, [len(ls)] + list(lengths[0])
    items, t, lengths = flattenNDlist(L)
    if t is None:
        lengths, flat = [0] * n, ''
    else:
        flat = ''.join(items)
    return pack('i' * len(lengths), *lengths) + flat, LRList(t, depth=n)

if useNumpy:
    @flattener(ndarray)
    def flattenArray(a):
        """Flatten numpy array to LabRAD list."""
        # TODO: respect type hints here.
        n = len(a.shape)
        dims = pack('i' * n, *a.shape)
        if a.dtype == dtype('bool'): t = LRBool()
        elif a.dtype == dtype('int32'): t = LRInt()
        elif a.dtype == dtype('uint32'): t = LRWord()
        elif a.dtype == dtype('int64'):
            a.dtype = 'uint32'
            a = a.flat[::2]
            t = LRWord()
        elif a.dtype == dtype('float64'): t = LRValue()
        elif a.dtype == dtype('complex128'): t = LRComplex()
        else:
            elems, types = zip(*[flatten(i) for i in a.flat])
            flat = dims + ''.join(elems)
            return flat, LRList(t, depth=n)
        flat = dims + a.tostring()
        return flat, LRList(t, depth=n)


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
