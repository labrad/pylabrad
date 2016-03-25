# Copyright (C) 2007  Matthew Neeley
# Copyright (C) 2014, Daniel Sank, Evan Jeffrey
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

import collections
import datetime
import itertools
import re
import struct
import sys
import time
from types import InstanceType
import warnings

import labrad.units as U
from labrad.units import Value, Complex

import numpy as np


SYSTEM_BYTE_ORDER = '<' if sys.byteorder == 'little' else '>'


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
_parsers = {} # type tag -> parse function


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
    """Consume strings without memory reallocation to improve performance."""

    def __init__(self, s):
        if isinstance(s, Buffer):
            self.s = s.s
            self.ofs = s.ofs
        else:
            self.s = s
            self.ofs = 0

    def get(self, i=1):
        """Get i characters from the buffer and increment pointer."""
        temp = self.s[self.ofs:self.ofs+i]
        self.ofs += i
        return temp

    def skip(self, i=1):
        """Increment pointer."""
        self.ofs += i

    def __len__(self):
        """Length of buffer which remains to be consumed."""
        return len(self.s) - self.ofs

    def __str__(self):
        """Returns unconsumed part of buffer."""
        return self.s[self.ofs:]

    def __getitem__(self, key):
        """Get part of unconsumed buffer indexed by key.

        If the current pointer is N and we call __getitem__(m), we get the
        character with absolute index N+m.

        This method reallocates the unconsumed part of the buffer to self.s
        and resets the offset pointer. That means we're doing string allocation,
        so don't use this for performance code.
        """
        self.s = self.s[self.ofs:]
        self.ofs = 0
        return self.s[key]

    def strip(self, chars):
        """Strip characters from the string and reallocate.

        Do not use this in performance code.
        """
        self.s = self.s[self.ofs:].strip(chars)
        self.ofs = 0
        return self

    def index(self, char):
        """Find index of char in uncomsumed part of buffer."""
        return self.s.index(char, self.ofs)


# typetag parsing

def parseTypeTag(s):
    """Parse a type tag into a LabRAD type object."""
    try:
        if isinstance(s, LRType):
            return s
        s = stripComments(s)
        ## this is a workaround for a bug in the manager
        ## What bug? This needs to be explained.
        if s == '' or s[:1] == '_':
            return LRNone()
        # Comments were already stripped, so why does the next line exist? DTS
        s = Buffer(stripComments(s))
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
    """Parse a single type at the beginning of a type string.

    s must be an instance of Buffer.
    """
    s.strip(WHITESPACE)
    # Consume one character to determine parsing function and then act that
    # parsing function of the remaining Buffer.
    t = _parsers[s.get()](s)
    s.strip(WHITESPACE)
    return t

COMMENTS = re.compile('\{[^\{\}]*\}')

def stripComments(s):
    """Remove comments from a type tag.

    Inline comments are delimited by curly brackets {} and may not be nested.
    In addition, anything after a colon : is considered a comment.
    """
    return COMMENTS.sub('', s).split(':')[0].strip()

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
_types = {} # python class -> LabRAD type

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

def getType(obj):
    """
    Get LabRAD type of python data.

    We try the following ways of finding of finding a suitible type, in order:

    obj.__lrtype__()
    _types[type(obj)]
    _typeFuncs[type(obj)](obj)
    _typeFuncs[superclasses of obj](obj)
    """
    if hasattr(obj, '__lrtype__'):
        return obj.__lrtype__()

    t = type(obj)

    if t == FlatData:
        return parseTypeTag(obj.tag)

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
    raise TypeError("No LabRAD type for: %r (type %s)" % (obj, type(obj)))


# flattening and unflattening

def unflatten(s, t, endianness='>'):
    """Unflatten labrad data into python data, given a prototype t.

    s - string or Buffer: data to be unflattened.
    t - string or LRType subclass: the prototype. If string this is a LabRAD
        type tag.

    The prototype can be a labrad type tag or a prototype object
    created the parseTypeTag function.  At present, the default
    unflatteners are called at each stage, according to t.
    """
    if isinstance(t, str):
        t = parseTypeTag(t)
    if isinstance(s, str):
        s = Buffer(s)
    return t.__unflatten__(s, endianness)


class FlatData(collections.namedtuple('FlatDataBase', ['bytes', 'tag', 'endianness'])):
    """FlatData represents unflattened data.

    Attributes:

        bytes:      The data as intended to be transmitted over the wire
        tag:        The LabRAD data type in the form of an LRType object.
        endianness: The endiannes of the connection. '>' for big endian
                    and '<' for little endian.  Little endian is deprecated.
    """
    __slots__ = ()
    def unflatten(self, endianness='>'):
        return unflatten(self.bytes, self.tag, self.endianness)
    
def flatten(obj, types=None, endianness='>'):
    """Flatten python data into labrad data.

    Returns a tuple containing the flattened string and the type object
    representing the LabRAD data type to which obj was flattened.

    Flatten returns a tuple of (flattened string, type object).  The
    type object can be converted into a type tag by calling str(typeobj).

    We first try obj.__lrflatten__(endianness). If that fails we go to the list
    of suggested types in order until one of them works. If none of them work,
    we raise FlatteningError.

    XXX This is worthless without a specification of __lrflatten__'s
    return signature.

    Suggested types can be provided in the form of type tags (strings) or type
    objects as created by parseTypeTag.

    If not types are provided, we first check to see if the object has
    an __lrflatten__ method, in which case it is used. Then, we check
    the registry of flattening functions to see whether one exists for the
    object's type, or one of its superclasses.

    If no types are provided, we first check to see if the object has
    an __lrflatten__ method, in which case it will be called.  Then we
    check the registry of flattening functions, to see whether one exists
    for the object type, or a superclass.
    """
    if hasattr(obj, '__lrflatten__'):
        s, t = obj.__lrflatten__(endianness)
        return FlatData(s, t, endianness)

    if types is None:
        types = []
    if not isinstance(types, list):
        types = [types]
    types = [parseTypeTag(t) for t in types]
    t = getType(obj)
    if not len(types):
        # if there are no type suggestions, just try to
        # flatten to the default type
        return t.flatten(obj, endianness)

    # check the list of allowed types for one compatible
    # with obj's type
    foundCompatibleType = False
    for tt in types:
        # If obj has a type which is more specific than one of the
        # allowed types, use obj's type. This covers cases where
        # an allowed type is 'v' and obj's type is 'v[Hz]'.
        if t <= tt:
            foundCompatibleType = True
            break
        # If one of the required types is more specific than obj's
        # type, use that. This covers cases where we're trying to
        # flatten something like ([],[1,2]) and an allowed type is
        # eg. (*v*i).
        elif tt <= t:
            t = tt
            foundCompatibleType = True
            break
    if foundCompatibleType:
        try:
            return t.flatten(obj, endianness)
        except Exception, e:
            raise FlatteningError(obj, t)

    # Since we haven't found anything compatible, just try to
    # flatten to any of the suggested types. This covers cases
    # such as an allowed type 'v[]' and obj=4. In this case, the
    # class representing 'v[]', namely LRValue(''), will handle
    # coercion of obj to the appropriate type.
    for t in types:
        try:
            return t.flatten(obj, endianness)
        except Exception:
            pass
        else:
            break

    raise FlatteningError(obj, types)


# Evaluation functions

def evalLRData(s):
    """Evaluate labrad data from string form produced by reprLRData.

    DEPRECATED

    The format produced by reprLRData has been deprecated, and this function
    is kept solely for backwards compatibility to load data stored with the
    old format.
    """

    # Value and Complex constructors previously allowed the unit parameter
    # to be None, and old data may have been saved that way. These shims
    # convert the unit to '' instead and then call the real constructors.
    def _Value(x, unit=''):
        if unit is None:
            unit = ''
        return U.Value(x, unit)

    def _Complex(x, unit=''):
        if unit is None:
            unit = ''
        return U.Complex(x, unit)

    globs = globals()
    globs['Value'] = _Value
    globs['Complex'] = _Complex
    globs['nan'] = float('nan')
    globs['inf'] = float('inf')
    return eval(s, globs)

def reprLRData(s):
    """Make a string repr of labrad data that can be parsed with evalLRData.

    DEPRECATED

    This was an attempt to create a human-readable string representation of
    labrad data suitable for storing small amounts of data and reading it
    in later. It was used in early versions of the data vault, and is kept
    here for backwards-compatibility only. This should not be used for new
    applications; instead, just use the standard wire-format for serialization.
    """
    return repr(s)


# LabRAD type classes

class LRType(object):
    """Base class of all LabRAD type objects.

    These type classes manage parsing and creation of type tags,
    provide default unflatteners, and also provide methods to test
    type equality and compatibility.
    """

    __metaclass__ = RegisterParser

    width = 0
    isFixedWidth = True

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
        """
        Parse type tag into appropriate python type objects.

        Returns the type object.

        The parse function takes the remaining string (after the tag for
        this type has been removed).  The function may need to consume
        some more of the string to determine the type.
        """
        return cls()

    @classmethod
    def __lrtype__(cls, obj):
        """
        Return the LabRAD type object for a python object.
        """
        return cls()

    def __cmp__(self, other):
        raise RuntimeError("Unreachable __cmp__ in LRType")

    def __eq__(self, other):
        """Test whether this type is equal to another.

        By default, we just check whether the types are the same.
        """
        return type(self) == type(other)

    def __le__(self, other):
        """
        Test whether this type is equal to on more specific than another.

        By default, just check for equality, or that the other type is LRAny.

        This operator has a very specific meaning which is easy to
        misunderstand. For two types, X and Y, X<=Y if and only if a setting
        advertising 'Y' will happily accept a LaBRAD record with data of type
        'X'. The simplest example of this is a setting accepting '?'. Such a
        setting will happily accept 'i', 'b', or anything else. Therefore, we
        have eg. LRInt()<=LRAny. A more complex example is 'v[Hz]' <= 'v'.
        """
        return type(self) == type(other) or type(other) == LRAny

    def isFullySpecified(self):
        return True

    def __width__(self, s, endianness):
        """
        Skip n bytes of tag buffer where n is width of this type.

        Returns number of bytes skipped.
        """
        s.skip(self.width)
        return self.width

    def __unflatten__(self, s, endianness):
        """Unflatten data from a string representation.

        Each LabRAD type object implements a default unflattener that
        creates python data from the LabRAD data string.  The unflattener
        returns a tuple of (python object, rest of string).
        """
        raise NotImplementedError

    def flatten(self, data, endianness):
        """Flatten an object to this Labrad type.

        This method deals with the case where incoming data has already been
        flattened. In that case, we check that the FlatData's type matches,
        otherwise for not-yet-flattened data we defer the real work to the
        __flatten__ method.

        Args:
            data (object or FlatData): If a FlatData is given, we just check
                that its type matches our type type and then return the already-
                flattened data. Otherwise, we call __flatten__.
            endianness (str): '<' for little- or '>' for big-endian.

        Returns:
            FlatData: The flattened data consisting of data and type tag.
        """
        if isinstance(data, FlatData):
            if not parseTypeTag(data.tag) <= self:
                raise FlatteningError(data, self)
            # TODO: @ejeffrey This is not an error, and we should
            # instead unflatten + flatten the data, possibly with a
            # warning, but I want to treat it as an error until this
            # is all working.
            if data.endianness != endianness:
                raise RuntimeError("Flattened data provided with wrong endianness")
            return data
        s, t = self.__flatten__(data, endianness)
        return FlatData(s, t, endianness)

    def __flatten__(self, data, endianness):
        """
        Flatten python data to this LabRAD type.

        Returns a tuple of (flattened string, LabRAD type object).

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
        return '', self

registerType(type(None), LRNone())
# register LRNone parser for the empty string as well
_parsers[''] = LRNone.__parse__


class LRBool(LRType, Singleton):
    """A simple boolean."""
    tag = 'b'
    width = 1

    def __unflatten__(self, s, endianness):
        return bool(ord(s.get(1)))

    def __flatten__(self, b, endianness):
        if not isinstance(b, (bool, np.bool8)):
            raise FlatteningError(b, self)
        return chr(b), self

registerType(bool, LRBool())
registerType(np.bool8, LRBool())

class LRInt(LRType, Singleton):
    """A signed 32-bit integer."""
    tag = 'i'
    width = 4
    def __unflatten__(self, s, endianness):
        return struct.unpack(endianness + 'i', s.get(4))[0]

    def __flatten__(self, n, endianness):
        if not isinstance(n, (int, long, np.integer)):
            raise FlatteningError(n, self)
        if n >= 0x80000000 or n < -0x80000000:
            raise ValueError("out of range for type i: {0}".format(n))
        return struct.pack(endianness + 'i', n), self

registerType(int, LRInt())
registerType(np.int32, LRInt())
registerType(np.int64, LRInt())


class LRWord(LRType, Singleton):
    """An unsigned 32-bit integer."""
    tag = 'w'
    width = 4
    def __unflatten__(self, s, endianness):
        return long(struct.unpack(endianness + 'I', s.get(4))[0])

    def __flatten__(self, n, endianness):
        if not isinstance(n, (int, long, np.integer)):
            raise FlatteningError(n, self)
        if n > 0xFFFFFFFF or n < 0:
            raise ValueError("out of range for type w: {0}".format(n))
        return struct.pack(endianness + 'I', n), self

registerType(long, LRWord())
registerType(np.uint32, LRWord())
registerType(np.uint64, LRWord())


class LRStr(LRType, Singleton):
    """A string of bytes prefixed by a 32-bit length field."""
    tag = 's'
    isFixedWidth = False

    def __width__(self, s, endianness):
        width = struct.unpack(endianness + 'i', s.get(4))[0]
        s.skip(width)
        return 4 + width

    def __unflatten__(self, s, endianness):
        n = struct.unpack(endianness + 'i', s.get(4))[0]
        return s.get(n)

    def __flatten__(self, s, endianness):
        if isinstance(s, unicode):
            s = s.encode('UTF-8')
        if not isinstance(s, str):
            raise FlatteningError(s, self)
        return struct.pack(endianness + 'I', len(s)) + s, self

registerType(str, LRStr())
registerType(unicode, LRStr())

class LRBytes(LRType, Singleton):
    """A raw 8-bit byte string."""
    tag = 'y'
    isFixedWidth = False

    def __width__(self, s, endianness):
        width = struct.unpack(endianness + 'i', s.get(4))[0]
        s.skip(width)
        return 4 + width

    def __unflatten__(self, s, endianness):
        n = struct.unpack(endianness + 'i', s.get(4))[0]
        return s.get(n)

    def __flatten__(self, s, endianness):
        if not isinstance(s, str):
            raise FlatteningError(s, self)
        return struct.pack(endianness + 'I', len(s)) + s, self

# Since bytes is an alias for str in python 2.7, don't enable this
# until we are ready to cut over.
# registerType(bytes, LRBytes)

def timeOffset():
    now = time.time()
    return (datetime.datetime(1904, 1, 1)
            - datetime.datetime.utcfromtimestamp(now)
            + datetime.datetime.fromtimestamp(now))

class LRTime(LRType, Singleton):
    """A timestamp in LabRAD format.

    Timestamp format comes from LabVIEW, and consists of two
    64-bit integers, representing seconds and fractions of a
    second since Jan. 1, 1904, UTC.
    """

    tag = 't'
    width = 16

    def __unflatten__(self, s, endianness):
        secs, us = struct.unpack(endianness + 'QQ', s.get(16))
        us = float(us) / pow(2, 64) * pow(10, 6)
        t = timeOffset() + datetime.timedelta(seconds=secs, microseconds=us)
        return t

    def __flatten__(self, t, endianness):
        diff = t - timeOffset()
        secs = diff.days * (60 * 60 * 24) + diff.seconds
        us = long(float(diff.microseconds) / pow(10, 6) * pow(2, 64))
        return struct.pack(endianness + 'QQ', secs, us), self

registerType(datetime.datetime, LRTime())

'''
class LRFloat(LRType, Singleton):
    tag = 'f'
    width = 8

    def __unflatten__(self, s, endianness):
        return struct.unpack(endianness + 'd', s.get(8)[0])

    def __flatten__(self, f, endianness):
        return struct.pack(endianness + 'd', f)

registerType(float, LRFloat)
'''

class LRValue(LRType):
    """Represents the type of a real number that carries units."""

    tag = 'v'
    width = 8

    # Types which can be flattened by LRValue as 'v[]' via coercion to
    # float. See __flatten__.
    CASTABLE_TYPES = [int, long]

    def __init__(self, unit=None):
        if isinstance(unit, U.Unit):
            unit = str(unit)
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
        # If other is 'v', then any variant of 'v' is allowed. For example, if
        # we are 'v[]' or 'v[Hz]', we are allowed to pass to a setting
        # advertising 'v'.
        if other.unit is None:
            return True
        if self.unit is None:
            msg = "Unreachable: no python object should get %s as type"%(self,)
            raise TypeError(msg)
        # We have a unit, and the other guy has a unit, so make sure our units
        # are compatible.
        return U.Unit(self.unit).isCompatible(U.Unit(other.unit))

    def isFullySpecified(self):
        return self.unit is not None

    def __unflatten__(self, s, endianness):
        v = struct.unpack(endianness + 'd', s.get(8))[0]
        if self.unit is not None:
            v = Value(v, self.unit)
        return v

    @classmethod
    def __lrtype__(cls, v):
        """
        Get a LRValue instance for a python object.

        We handle the follwing types:
            float -> LRValue('')
            labrad.units.Value(unit) -> LRValue(str(unit))
        """
        if isinstance(v, U.WithUnit):
            return cls(v.unit)
        elif isinstance(v, (float, U.DimensionlessFloat)):
            return cls('')
        else:
            raise TypeError("No %s type for %s"%(cls, v))

    def __flatten__(self, v, endianness):
        v = self.__check_units__(v)
        v = float(v)
        # If we are an LRValue(None), switch to LRValue('') so that wire
        # data has correct type tag, eg. 'v[]' instead of 'v'.
        if self.unit is None:
            self.unit = ''
        return struct.pack(endianness + 'd', float(v)), self

    def __check_units__(self, v):
        # TODO: implement full labrad unit conversion semantics in pylabrad
        # If v is not a unit-full object, only accept if our unit is
        # None or ''.
        if not isinstance(v, U.WithUnit):
            if self.unit is not None and self.unit != '':
                raise FlatteningError(v, self)
        else:
            # v has units, so convert to required units.
            v = v[self.unit]
        return v

registerTypeFunc((float, Value), LRValue.__lrtype__)


class LRComplex(LRValue):
    """Represents the type of a complex number that carries units."""

    tag = 'c'
    width = 16

    def __unflatten__(self, s, endianness):
        real, imag = struct.unpack(endianness + 'dd', s.get(16))
        c = complex(real, imag)
        if self.unit is not None:
            c = Complex(c, self.unit)
        return c

    def __flatten__(self, c, endianness):
        c = self.__check_units__(c)
        c = complex(c)
        if self.unit is None:
            self.unit = ''
        return struct.pack(endianness + 'dd', c.real, c.imag), self

    @classmethod
    def __lrtype__(cls, c):
        if isinstance(c, U.WithUnit):
            return cls(c.unit)
        elif isinstance(c, (complex, U.DimensionlessComplex)):
            return cls('')
        else:
            raise TypeError("No %s type for %s"%(cls, c))

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

    def partial_unflatten(self, s, endianness):
        """Unflatten a cluster into a tuple of FlatData objects"""
        s = Buffer(s)
        s2 = Buffer(s)
        item_sizes = [item.__width__(s, endianness) for item in self.items]
        return tuple(FlatData(s2.get(item_size), item, endianness)
                     for (item, item_size) in zip(self.items, item_sizes))

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
                    flat = flatten(elem, endianness=endianness)
                    strs.append(flat.bytes)
                    items.append(flat.tag)
                else:
                    flat = t.flatten(elem, endianness)
                    strs.append(flat.bytes)
                    items.append(flat.tag)
            self.items = items # warning: type mutated here
            return ''.join(strs), self
        return ''.join(t.flatten(elem, endianness).bytes for t, elem in zip(self.items, c)), self

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
#                    flat = t.flatten(elem, endianness)
#                    strs.append(flat.bytes)
#                    items.append(flat.tag)
#            self.items = items # warning: type mutated here
#            return ''.join(strs)
#        return ''.join(t.flatten(elem, endianness) for t, elem in zip(self.items, c))


class LRList(LRType):
    """A multidimensional rectangular array type."""

    tag = '*'

    ARRAY_TYPES = [LRValue(), LRComplex(), LRInt(), LRWord(), LRBool()]

    def __init__(self, elem=LRNone(), depth=1):
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
        dims = struct.unpack(endianness + ('i'*n), s.get(4*n))
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
            t = LRNone() # empty list
            s.get() # drop underscore
        else:
            t = parseSingleType(s)
        return cls(t, n)

    @classmethod
    def __lrtype__(cls, L):
        """
        Return a type object for L.
        """
        depth, temp = 1, L
        while len(temp) and isinstance(temp[0], list):
            depth, temp = depth+1, temp[0]

        def iterND(ls):
            if len(ls) and isinstance(ls[0], list):
                return itertools.chain(*(iterND(i) for i in ls))
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
        elif L.dtype in ['>i8', '<i8']: t = LRInt()
        elif L.dtype in ['>u4', '<u4']: t = LRWord()
        elif L.dtype in ['>u8', '<u8']: t = LRWord()
        elif L.dtype in ['>f8', '<f8']: t = LRValue('')
        elif L.dtype in ['>c16', '<c16']: t = LRComplex('')
        else:
            raise Exception("Can't flatten array of %s" % L.dtype)
        return cls(t, depth=len(L.shape))

    @classmethod
    def __lrtype_ValueArray__(cls, L):
        if L[L.unit].dtype in ['>c16', '<c16']:
            t = LRComplex(L.unit)
        else:
            t = LRValue(L.unit)
        return cls(t, depth=len(L._value.shape))

    def __le__(self, other):
        """Test whether this type is more specific than another.

        We check the list dimensionality (depth) and the element type.
        """
        return (type(other) == LRAny or
                (type(self) == type(other) and
                 self.depth == other.depth and
                 (other.elem is None or type(other.elem) == LRNone or self.elem <= other.elem)))

    def __eq__(self, other):
        """Test whether this type is equal to another.

        We check the list dimensionality (depth) and the element type.
        """
        return (type(self) == type(other) and
                self.depth == other.depth and
                self.elem == other.elem)

    def isFullySpecified(self):
        return type(self.elem) != LRNone and self.elem.isFullySpecified()

    def __unflatten__(self, s, endianness):
        """Unflatten to numpy array if possible, or else nested python list."""
        n, elem = self.depth, self.elem
        dims = struct.unpack(endianness + ('i'*n), s.get(4*n))
        size = np.prod(dims)

        # Attempt to unflatten as numpy array.
        for t in self.ARRAY_TYPES:
            if elem is not None and elem <= t:
                return self._unflatten_as_array(s, endianness, elem, dims, size)

        # Unflatten as nested python list.
        if self.elem is None or size == 0:
            result = nestedList([], n-1)
        else:
            def unflattenNDlist(s, dims):
                if len(dims) == 1:
                    return [unflatten(s, self.elem, endianness) for _ in xrange(dims[0])]
                else:
                    return [unflattenNDlist(s, dims[1:]) for _ in xrange(dims[0])]
            result = unflattenNDlist(s, dims)
        return LazyList(result)

    def _unflatten_as_array(self, s, endianness, elem, dims, size):
        """Unflatten to numpy array."""
        def make(t, width):
            a = np.fromstring(s.get(size*width), dtype=np.dtype(t))
            if endianness != SYSTEM_BYTE_ORDER:
                a.byteswap(True) # inplace
            return a

        if elem == LRBool(): a = make('bool', 1)
        elif elem == LRInt(): a = make('i4', 4)
        elif elem == LRWord(): a = make('u4', 4)
        elif elem <= LRValue(): a = make('f8', 8)
        elif elem <= LRComplex(): a = make('c16', 16)
        else:
            raise TypeError("Cannot make numpy array with %s"%(elem,))
        a.shape = dims + a.shape[1:] # handle clusters as elements
        if elem <= LRValue() or elem <= LRComplex():
            if elem.unit is not None and elem.unit != '':
                a = U.ValueArray(a, elem.unit)
            else:
                a = U.DimensionlessArray(a)
        return a

    def __flatten__(self, L, endianness):
        """Flatten (nested) python list to LabRAD list.

        Lists must be homogeneous and rectangular.
        """
        if isinstance(L, np.ndarray):
            if (self.elem <= LRValue() and
                    not (self.elem.unit is None or self.elem.unit == '')):
                msg = "Can't flatten ndarray to {}".flatten(self)
                raise TypeError(msg)
            return self.__flatten_array__(L, endianness)
        if isinstance(L, U.ValueArray):
            return self.__flatten_ValueArray__(L, endianness)
        if self.elem == LRAny():
            self.elem = self.__lrtype__(L).elem
        lengths = [None] * self.depth
        def flattenNDlist(ls, n=0):
            if lengths[n] is None:
                lengths[n] = len(ls)
            if len(ls) != lengths[n]:
                raise Exception('List is not rectangular.')
            if n+1 == self.depth:
                return ''.join(self.elem.flatten(e, endianness).bytes for e in ls)
            else:
                return ''.join(flattenNDlist(row, n+1) for row in ls)
        flat = flattenNDlist(L)
        lengths = [l or 0 for l in lengths]
        return struct.pack(endianness + ('i' * len(lengths)), *lengths) + flat, self

    def __flatten_array__(self, a, endianness):
        """Flatten numpy array to LabRAD list."""
        shape = a.shape[:self.depth]
        if len(shape) != self.depth:
            raise Exception("Bad array shape.")
        dims = struct.pack(endianness + ('i' * len(shape)), *shape)
        if self.elem == LRAny():
            self.elem = self.__lrtype_array__(a).elem

        # determine what dtype we would like to have
        wanted_dtype = _known_dtypes.get(type(self.elem), None)

        if wanted_dtype is not None:
            if wanted_dtype == 'u4':
                if a.dtype in ['<i8', '>i8']:
                    a = a.astype(endianness + 'u4')
            wanted_dtype = np.dtype(endianness + wanted_dtype)
            if a.dtype != wanted_dtype:
                a_cast = a.astype(wanted_dtype)
                # make sure values don't change in a narrowing cast
                if a.dtype.itemsize > wanted_dtype.itemsize and (not np.all(a_cast == a)):
                    raise Exception("Narrowing typecast loses information while flattening numpy array: dtype={0}, wanted_dtype={1}".format(a.dtype, wanted_dtype))
                a = a_cast
        else:
            elems = (flatten(i, endianness=endianness).bytes for i in a.flat)
            return dims + ''.join(elems), self
        return dims + a.tostring(), self

    def __flatten_ValueArray__(self, va, endianness):
        # Convert to appropriate unit and flatten as array
        numericalData = va[self.elem.unit]
        return self.__flatten_array__(numericalData, endianness)


_known_dtypes = {
    LRBool: 'u1',
    LRInt: 'i4',
    LRWord: 'u4',
    LRValue: 'f8',
    LRComplex: 'c16'
}

registerTypeFunc(list, LRList.__lrtype__)
registerTypeFunc(np.ndarray, LRList.__lrtype_array__)
registerTypeFunc(U.ValueArray, LRList.__lrtype_ValueArray__)
registerTypeFunc(U.DimensionlessArray, LRList.__lrtype_array__)


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
        s, t, _ = flatten((int(code), str(msg), payload), t, endianness)
        self.payload = t.items[2]
        return s, self

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
        s, t, _ = flatten((self.code, self.msg, self.payload), endianness=endianness)
        return s, LRError(t.items[2])

class Int(int):
    def __lrtype__(self):
        return LRInt()

class Word(int):
    def __lrtype__(self):
        return LRWord()


class LazyList(list):
    """A proxy object for LabRAD lists.

    List unflattening is not actually done lazily; this class is kept just to
    provide the stub methods below, which now emit deprecation warnings when
    called. This class will be removed in a future release.
    """

    @property
    def aslist(self):
        warnings.warn("LazyList.aslist is deprecated. List unflattening is no "
                      "longer lazy, so this is not needed.")
        return list(self)

    @property
    def astuple(self):
        warnings.warn("LazyList.astuple is deprecated. Use tuple() instead.")
        return tuple(self)

    @property
    def asarray(self):
        warnings.warn("LazyList.asarray is deprecated. Use np.asarray() instead.")
        return np.ndarray(self)


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
