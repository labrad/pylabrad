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


# Physical quantities with units
#
# Written by Konrad Hinsen <hinsen@cnrs-orleans.fr>
# with contributions from Greg Ward
# last revision: 2007-5-25


"""
Physical quantities with units.

This module provides a data type that represents a physical
quantity together with its unit. It is possible to add and
subtract these quantities if the units are compatible, and
a quantity can be converted to another compatible unit.
Multiplication, subtraction, and raising to rational powers
is allowed without restriction, and the result will have
the correct unit.

The values of physical constants are taken from the 1986
recommended values from CODATA. Other conversion factors
(e.g. for British units) come from various sources. I can't
guarantee for the correctness of all entries in the unit
table, so use this at your own risk.

This module is based on code from the ScientificPython package.
The version included with LabRAD has been slightly changed:

    - removed depency on numpy or numeric
    - included NumberDict so the module is self-contained
    - units that cannot be converted to SI are kept as text alone
    - physical quantity types are derived from numeric types, and the
      WithUnit mixin class.  Hence, they can be used directly as numbers
    - Value and Complex types define a __getitem__ method to
      express the value in a new unit, e.g:
      >>> Value(1, 'GHz')['Hz'] -> 1e9

"""

from fractions import Fraction
from math import floor, pi

import numpy as np

from labrad import grammar
from labrad.util import cache

# Dictionary containing numbers
#
# These objects are meant to be used like arrays with generalized
# indices. Non-existent elements default to zero. Global operations
# are addition, subtraction, and multiplication/division by a scalar.
#
# Written by Konrad Hinsen <hinsen@cnrs-orleans.fr>
# last revision: 2006-10-16

class NumberDict(dict):
    """
    Dictionary storing numerical values

    Constructor: NumberDict()

    An instance of this class acts like an array of number with
    generalized (non-integer) indices. A value of zero is assumed
    for undefined entries. NumberDict instances support addition,
    and subtraction with other NumberDict instances, and multiplication
    and division by scalars.
    """

    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            return 0

    def __coerce__(self, other):
        if isinstance(other, dict):
            other = NumberDict(other)
        return self, other

    def __neg__(self):
        for key in self:
            self[key] *= -1

    def __add__(self, other):
        sum_dict = NumberDict()
        for key in self.keys():
            sum_dict[key] = self[key]
        for key in other.keys():
            sum_dict[key] = sum_dict[key] + other[key]
        return sum_dict

    def __sub__(self, other):
        sum_dict = NumberDict()
        for key in self.keys():
            sum_dict[key] = self[key]
        for key in other.keys():
            sum_dict[key] = sum_dict[key] - other[key]
        return sum_dict

    def __mul__(self, other):
        new = NumberDict()
        for key in self.keys():
            new[key] = other * self[key]
        return new

    __rmul__ = __mul__

    def __div__(self, other):
        new = NumberDict()
        for key in self.keys():
            new[key] = self[key] / other
        return new


class Lazy(object):
    """A method decorator which converts methods to lazy properties.

    A lazy property is computed on demand the first time it is accessed,
    and the result of the computation is then stored in the object's instance
    __dict__ so that subsequent access is just a dict lookup and incurs no
    overhead from descriptor access.

    Example use:

    class Foo(object):
        @Lazy
        def bar(self):
            return intense_computation(self, ...)

    >>> foo = Foo()
    >>> result_first_access = foo.bar
    # Incurs long computation. Note the lack of ().

    >>> result_second_access = foo.bar
    # Incurs no computation. Looks up previously computed and cached result.

    Methods decorated by Lazy must take no arguments aside from the implicit
    self argument and must return a deterministic result. Also note that the
    decorated method is accessed as an attribute, i.e. no ().

    Attributes:
        f (function): The decorated function. f is called only the first time
            the decorated method is accessed.
    """

    def __init__(self, f):
        """Initialize a Lazy property

        Args:
            f (function): The function to by lazified.

        Returns nothing. However, Lazy is used as a decorator on methods, so
        Lazy.__new__ is called automatically at class creation time and returns
        a Lazy instance which wraps the original method f.
        """
        self.f = f

    def __get__(self, obj, objtype=None):
        result = self.f(obj)
        obj.__dict__[self.f.__name__] = result
        return result


class WithUnit(object):
    """Mixin class for adding units to numeric types.

    Quantities with units can be used with basic arithmetic operations
    (addition, subtraction, multiplication, division, raising to powers).

    The 'unit' property stores the units for a given quantity, and you
    can get the bare value converted to a particular unit 'u' by using
    square-bracket indexing with the name of a unit or a unit object:

    >>> x = Value(1, 's')
    >>> x
    Value(1.0, 's')
    >>> x.unit
    <Unit 's'>
    >>> x['ms']
    1000.0

    To just strip off the units, you can use the square bracket indexing
    with the 'unit' property. For example, if you wanted to print the value
    and units separately:

    >>> print "The value is {:3.2f} {}".format(x[x.unit], x.unit)
    1.00 s
    """

    __array_priority__ = 15

    def __new__(cls, value, unit=None):
        # Convert inputs to make sense:
        # check for illegal None unit, unit string -> Unit, list -> array, check
        # to see if value is
        if unit is None:
            raise RuntimeError("Cannot construct WithUnit with unit=None.  Use correct units, or use a float")
        if isinstance(value, list):
            value = np.asarray(value)
        unit = Unit(unit)
        if hasattr(value, 'unit'): # This is called from Unit * Value and friends
            return WithUnit(value._value, value.unit * unit)

        # Ok, with all that business taken care of, look up the right type
        # (Value, Complex, ValueArray, or the Dimensionless versions of each
        # and construct a final object
        cls = cls._findClass(type(value), unit)
        if unit and unit.is_dimensionless:
            return cls(value * unit.conversionFactorTo(''))
        inst = super(WithUnit, cls).__new__(cls)
        inst._value = inst._numType(value) * 1.0 # For numpy: int to float
        inst.unit = Unit(unit)
        inst.is_dimensionless = inst.unit is None or inst.unit.is_dimensionless
        return inst

    _numericTypes = {}
    _dimensionlessTypes = {}

    @classmethod
    def _findClass(cls, numType, unit):
        """Find a class for a particular numeric type and unit.

        Classes will be created if they haven't been already.
        """
        # find class with units for this numeric type
        try:
            if unit.is_dimensionless:
                cls = cls._dimensionlessTypes[numType]
            else:
                cls = cls._numericTypes[numType]
        except KeyError:
            raise TypeError('Cannot use units with instances of type %s' % (numType,))
        return cls

    def __reduce__(self):
        return (WithUnit, (self._value, self.unit.name))

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __str__(self):
        return '%s %s' % (self._value, self.unit)

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__, self._value, self.unit.name)

    @property
    def units(self):
        """A string representation of the unit of this value."""
        return self.unit.name

    def _convert_units(self, other):
        """Convert two objects to use compatible units.

        This is used by __add__ and __sub__ as well as the __lt__ family of comparison
        operators.  This repalces the old __cmp__ based operation which didn't work on
        inf and nans.

        This returns (left, right, unit) where 'left' and 'right' are bare numeric types
        (float, complex, array), and unit is their common unit.
        """
        if isinstance(other, WithUnit):
            if self.isCompatible(other):
                if self.unit.conversionFactorTo(other.unit) > 1:
                    unit = other.unit
                else:
                    unit = self.unit
                return (self[unit], other[unit], unit)
            else:
                raise TypeError("Incompatible units: %s, %s" % (self.unit, other.unit))
        elif self.is_dimensionless:
            return (self[''], other, U.Unit(''))
        elif other == 0:
            return (self._value, 0.0, self.unit)
        else:
            raise TypeError("Incompatible Units %s, ''" % (self.unit,))

    def __add__(self, other):
        a, b, unit = self._convert_units(other)
        return WithUnit(a+b, unit)

    __radd__ = __add__

    def __sub__(self, other):
        a, b, unit = self._convert_units(other)
        return WithUnit(a-b, unit)

    def __rsub__(self, other):
        a, b, unit = self._convert_units(other)
        return WithUnit(b-a, unit)

    def __eq__(self, other):
        try:
            a, b, unit = self._convert_units(other)
            return a==b
        except Exception as e:
            # Anything that prevents comparison means and b are not equal
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        a, b, unit = self._convert_units(other)
        return a < b

    def __le__(self, other):
        a, b, unit = self._convert_units(other)
        return a <= b

    def __gt__(self, other):
        a, b, unit = self._convert_units(other)
        return a > b

    def __ge__(self, other):
        a, b, unit = self._convert_units(other)
        return a >= b

    def __mul__(self, other):
        if isinstance(other, Unit):
            return WithUnit(self._value, self.unit * other)
        if isinstance(other, WithUnit):
            return WithUnit(self._value * other._value,
                            self.unit * other.unit)
        return WithUnit(self._value * other, self.unit)

    __rmul__ = __mul__

    def __div__(self, other):
        if isinstance(other, Unit):
            return WithUnit(self._value, self.unit / other)
        if isinstance(other, WithUnit):
            return WithUnit(self._value / other._value,
                            self.unit / other.unit)
        return WithUnit(self._value / other, self.unit)

    __truediv__ = __div__

    def __rdiv__(self, other):
        if isinstance(other, Unit):
            return WithUnit(self._value, other / self.unit)
        if isinstance(other, WithUnit):
            return WithUnit(other._value / self._value,
                            other.unit / self.unit)
        return WithUnit(other / self._value, pow(self.unit, -1))

    __rtruediv__ = __rdiv__

    def __pow__(self, other):
        if isinstance(other, (WithUnit, Unit)) and not other.is_dimensionless:
            raise TypeError('Exponents must be dimensionless')
        return WithUnit(pow(self._value, float(other)),
                        pow(self.unit, other))

    def __rpow__(self, other):
        if not self.is_dimensionless:
            raise TypeError('Exponents must be dimensionless')
        return pow(other, self._value * self.unit.factor)

    def __abs__(self):
        return WithUnit(abs(self._value), self.unit)

    def __pos__(self):
        return self

    def __neg__(self):
        return WithUnit(-self._value, self.unit)

    def __nonzero__(self):
        return self._value != 0

    def __hash__(self):
        '''
        Not sure if using Value as a dictionary key makes sense, but
        here it is anyway.  We convert to base units so that 1*km and
        1000*m hash to the same value.  They also hash to the same
        value as 1000*V, but that is OK.  Note that this is still kind
        of messed up: 1001*m != 1.001*km because the latter is not an
        exact number.  C'est la floating point.
        '''
        if not hasattr(self, '_hash'):
            self._hash = hash(self._base_value)
        return self._hash

    @Lazy
    def _base_value(self):
        """The bare value of this WithUnit in units of our base unit.

        This is used internally for performance reasons in certain contexts,
        but should not be used externally.
        """
        return self[self.unit.base_unit]

    def __getitem__(self, unit):
        """Return value of physical quantity expressed in new units."""
        if unit == self.unit:
            return self._value
        factor, offset = self.unit.conversionTupleTo(unit)
        return (self._value + offset) * factor

    def inUnitsOf(self, unit):
        """
        Express the quantity in different units. If one unit is
        specified, a new PhysicalQuantity object is returned that
        expresses the quantity in that unit. If several units
        are specified, the return value is a tuple of
        PhysicalObject instances with with one element per unit such
        that the sum of all quantities in the tuple equals the the
        original quantity and all the values except for the last one
        are integers. This is used to convert to irregular unit
        systems like hour/minute/second.

        @param unit: one or several units
        @type unit: C{str}
        @returns: one or more physical quantities
        @rtype: L{PhysicalQuantity} or C{tuple} of L{PhysicalQuantity}
        @raises TypeError: if any of the specified units are not compatible
        with the original unit
        """
        if unit == self.unit:
            return self
        u = Unit(unit)
        return self[u] * u

    # Contributed by Berthold Hoellmann
    def inBaseUnits(self):
        """
        @returns: the same quantity converted to base units,
        i.e. SI units in most cases
        @rtype: L{PhysicalQuantity}
        """
        return self.inUnitsOf(self.unit.base_unit)

    def isCompatible(self, unit):
        """
        @param unit: a unit
        @type unit: C{str}
        @returns: C{True} if the specified unit is compatible with the
        one of the quantity
        @rtype: C{bool}
        """
        return self.unit.isCompatible(unit)

    def isDimensionless(self):
        return self.is_dimensionless

    def sqrt(self):
        return np.sqrt(self._value) * pow(self.unit, Fraction(1, 2))


class Value(WithUnit):
    _numType = float

    def __float__(self):
        return self['']

    def __iter__(self):
        raise TypeError("'Value' object is not iterable")

WithUnit._numericTypes[float] = Value
WithUnit._numericTypes[int] = Value
WithUnit._numericTypes[long] = Value
WithUnit._numericTypes[np.int32] = Value
WithUnit._numericTypes[np.int64] = Value


class Complex(WithUnit):
    _numType = complex

    def __complex__(self):
        return self['']

    def __iter__(self):
        raise TypeError("'Complex' object is not iterable")

WithUnit._numericTypes[complex] = Complex


class ValueArray(WithUnit):

    _numType = np.array # Regular ndarray constructor doesn't work

    def __new__(cls, data, unit=None):
        '''
        unit=None can only be used if data is an iterable of items that already have units
        '''
        if unit is not None:
            return super(ValueArray, cls).__new__(cls, data, unit)

        it = iter(data)
        first = it.next()
        unit = first.unit
        first = first[unit] # convert to float
        rest = [x[unit] for x in it]
        return WithUnit([first] + rest, unit)

    def __copy__(self):
        # Numpy arrays are not immutable so we have to
        # make a real copy
        return WithUnit(self._value.copy(), self.unit)

    def __deepcopy__(self, memo):
        return self.__copy__()

    def __getitem__(self, unit):
        if isinstance(unit, (str, Unit)):
            """Return value of physical quantity expressed in new units."""
            return super(ValueArray, self).__getitem__(unit)
        else:
            idx = unit
            return WithUnit(self._value[idx], self.unit)

    def __setitem__(self, key, value):
        self._value[key] = value.inUnitsOf(self.unit)._value

    def __len__(self):
        return len(self._value)

    # expose useful attributes from the backing array

    @property
    def dtype(self):
        return self._value.dtype

    @property
    def ndim(self):
        return self._value.ndim

    @property
    def shape(self):
        return self._value.shape

    def allclose(self, other, *args, **kw):
        return np.allclose(self._value, other[self.unit], *args, **kw)

WithUnit._numericTypes[np.ndarray] = ValueArray
WithUnit._numericTypes[list] = ValueArray

# add support for numeric types returned by most numpy/scipy functions
WithUnit._numericTypes[np.float64] = Value
WithUnit._numericTypes[np.complex128] = Complex

# Unit class implementation
#
# Unit class attributes:
#       powers:         9 element list of the power of each SI base unit
#       lex_names:      Number Dictionary of non-SI "base" units (i.e., {'counts': 1}).  
#       names:          (Number)-Dictionary of display names with the associated powers
#       factor:         Ratio between the unit value described by 'names', and the base
#                       units described by powers and lex_names.
#       offset:         Offset from zero used for degF and degC.
#
# So, for example, the unit representation of a few types are given here:
#
# N [newton]: names: {'N': 1}, powers: [1, 1, -2, 0, ...] lex_names: {}, factor: 1.0
# l/s [liter/sec]: names: {'l': 1, 's': -1} powers: [3, 0, -1, 0...] lex_names: {}, factor: .001
# kN: names: {'kN': 1}, powers: [1, 1, -2, 0, ...], lex_names: {}, factor: 1000
# 'count': names: {'count': 1}, powers: [0, 0, 0,...] lex_names: {'count': 1}, factor: 1
#
# The important invariant is that 'names' (the display name) should contain the display
# equivalents to the base units stored in powers (for SI derived units) and lex_names
# (for custom units).
#
# names and lex_names are instances of the NumberDict type.
# NumberDict works like a standard dictionary, except that the keys
# are numeric values, which are used to store the power of each unit
# element.  In addition to normal dictionary access, NumberDicts
# support addition and subtraction.  Adding two NumberDict's merges
# their keys, adding the values of matching keys together.  
#
# There are a few more attributes computed from the above attributes as optimzations:
#
# _name:                The computed name in string form.  For instance, if
#                       names={'km': 1, 'l': -1}, _name will be 'km/l'.  _name
#                       is computed on-demand.
# is_dimensionless:     if powers is all zeros and lex_names is empty, the unit is dimensionless
# is_angle:             If the only non-zero element in powers is 'radians' and lex_names is empty
#
# Unit instances are registered in the module level _unit_table
# dictionary.  This allows you to say Unit('N'), and have it look up
# the right object (including the SI base unit factors).

class Unit(object):
    """Unit of measurement

    A unit is defined by a name (possibly composite), a scaling factor,
    and the exponentials of each of the SI base units that enter into
    it. Units can be multiplied, divided, and raised to rational powers.
    """

    __array_priority__ = 15

    def __new__(cls, *args, **kw):
        """Construct a new unit instance.

        Units can be constructed in several ways:
            one argument: a Unit, WithUnit or str
            three arguments: name, factor, and Unit, WithUnit or str
            otherwise: arguments passed to _init on a new instance
        """
        if len(args) == 1:
            unit = args[0]
            if isinstance(unit, Unit):
                return unit
            elif isinstance(unit, WithUnit):
                return unit.unit
            elif isinstance(unit, str):
                return cls._parse(unit)
            raise Exception('Cannot create Unit for %r' % unit)
        elif len(args) == 3 and isinstance(args[2], (Unit, WithUnit, str)):
            # construct a named unit that is equal to a
            # previously-defined unit, times a factor
            name, factor, unit = args[:3]
            factor = float(factor)
            if isinstance(unit, WithUnit):
                unit, factor = unit.unit, factor * unit._value
            elif isinstance(unit, str):
                unit = cls._parse(unit)
            inst = Unit(name, factor * unit.factor,
                        unit.powers, unit.offset, unit.lex_names)
            return inst
        # construct a new unit
        inst = super(Unit, cls).__new__(cls)
        inst._init(*args, **kw)
        return inst

    def __reduce__(self):
        return (Unit, (self.name,))

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    @classmethod
    def _parse(cls, name):
        if name in _unit_table:
            return _unit_table[name]
        unit = _unit_table[''] # start with identity
        try:
            parsed = grammar.unit.parseString(name)
            for sign, list_ in [(1, parsed.posexp), (-1, parsed.negexp)]:
                if isinstance(list_, str):
                    continue
                for elem in list_:
                    num = elem['num'] if 'num' in elem else 1
                    num = -num if 'neg' in elem else num
                    denom = elem['denom'] if 'denom' in elem else 1
                    term = elem['name']
                    if term not in _unit_table:
                        _unit_table[term] = cls._stringUnit(term)
                    unit = unit * _unit_table[term]**(sign*Fraction(num, denom))
        except Exception:
            # TODO handle errors more intelligently here.
            # (might need to change unit grammar)
            # most likely this was a parsing error
            # the manager doesn't guarantee that units
            # will follow the grammar, so not handling this
            # error can crash us and kill our connection.
            # For now, just fall back to a string unit in this case.
            unit = cls._stringUnit(name)
        # if the name of this unit is new, we'll add it to the table
        # of known units.  Otherwise, we'll just return the unit
        # object that is already in the table.  This means units that
        # parse to the same name will end up being the same object.
        return _unit_table.setdefault(unit.name, unit)

    @staticmethod
    def _stringUnit(name):
        """Create a unit that has a name, but is outside the usual SI system."""
        return Unit(NumberDict([(name, 1)]), 1., [0]*9, 0, name)

    def _init(self, names, factor, powers, offset=0, lex_names=''):
        """
        @param names: a dictionary mapping each name component to its
                      associated power (e.g. C{{'m': 1, 's': -1}})
                      for M{m/s}). As a shorthand, a string may be passed
                      which is assigned an implicit power 1.
        @type names: C{dict} or C{str}
        @param factor: a scaling factor
        @type factor: C{float}
        @param powers: the integer powers for each of the nine base units
        @type powers: C{list} of C{int}
        @param offset: an additive offset to the base unit (used only for
                       temperatures)
        @type offset: C{float}
        @param lex_names: a dictionary mapping named components to their
                          associated powers.  lex_names cannot be converted
                          to SI units, but are instead treated as base units
                          themselves.
        @type lex_names: C{dict} or C{str}
        """
        if isinstance(names, str):
            self.names = NumberDict()
            self.names[names] = Fraction(1)
        else:
            self.names = names
        self.factor = factor
        self.offset = offset
        self.powers = [Fraction(p) for p in powers]
        if isinstance(lex_names, str):
            self.lex_names = NumberDict()
            if lex_names:
                self.lex_names[lex_names] = Fraction(1)
        else:
            self.lex_names = lex_names
        self.is_dimensionless = not any(self.powers) and not any(self.lex_names.values())
        self.is_angle = (self.powers[7] == 1 and
                        not any(self.powers[0:7]) and
                        not self.powers[8] and
                        not any(self.lex_names.values()))

    @Lazy
    def name(self):
        num = ''
        denom = ''
        if all(power < 0 for unit, power in self.names.items()):
            # if all powers are negative, use negative exponents
            for unit, power in self.names.items():
                unit += '^' + str(power)
                num += '*' + unit
        else:
            # if some powers are positive, use num/denom
            for unit, power in self.names.items():
                if power != 1 and power != -1:
                    unit += '^' + str(abs(power))
                if power < 0: denom += '/' + unit
                elif power > 0: num += '*' + unit
        num = num[1:] if len(num) else '1' # remove leading '*' from numerator
        name = num + denom
        if name == '1':
            name = ''
        self._name = name
        if name not in _unit_table:
            _unit_table[name] = self
        return name

    @Lazy
    def base_unit(self):
        num = ''
        denom = ''
        for unit, power in (zip(_base_names, self.powers) +
                            self.lex_names.items()):
            if power != 1 and power != -1:
                unit += '^' + str(abs(power))
            if power < 0: denom += '/' + unit
            elif power > 0: num += '*' + unit
        if not len(num):
            num = '1'
        else:
            num = num[1:] # strip leading '*'
        name = num + denom
        if name == '1':
            name = ''
        return Unit(name)

    def __repr__(self):
        return "<Unit '%s'>" % self.name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, str):
            try:
                return self.name == other or self == Unit(other)
            except Exception:
                # might fail to convert other to Unit
                pass
        elif isinstance(other, Unit):
            return (self.factor == other.factor and
                    self.offset == other.offset and
                    self.powers == other.powers and
                    self.lex_names == other.lex_names)
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @cache.lru_cache()
    def _mul_units(self, other):
        if self.offset != 0 or other.offset != 0:
            raise TypeError("cannot multiply units with non-zero offset: '%s', '%s'" % (self, other))
        return Unit(self.names + other.names,
                    self.factor * other.factor,
                    [a + b for a, b in zip(self.powers, other.powers)],
                    self.offset,
                    self.lex_names + other.lex_names)

    def __mul__(self, other):
        if isinstance(other, Unit):
            return self._mul_units(other)
        return WithUnit(other, self)

    __rmul__ = __mul__

    @cache.lru_cache()
    def _div_units(self, other):
        if self.offset != 0 or other.offset != 0:
            raise TypeError("cannot divide units with non-zero offset: '%s', '%s'" % (self, other))
        return Unit(self.names - other.names,
                    self.factor / other.factor,
                    [a - b for a, b in zip(self.powers, other.powers)],
                    self.offset,
                    self.lex_names - other.lex_names)

    def __div__(self, other):
        if isinstance(other, Unit):
            return self._div_units(other)
        return WithUnit(1.0 / other, self)

    @cache.lru_cache()
    def _rdiv_units(self, other):
        if self.offset != 0 or other.offset != 0:
            raise TypeError("cannot divide units with non-zero offset: '%s', '%s'" % (self, other))
        return Unit(other.names - self.names,
                    other.factor / self.factor,
                    [a - b for a, b in zip(other.powers, self.powers)],
                    self.offset,
                    other.lex_names - self.lex_names)

    def __rdiv__(self, other):
        if isinstance(other, Unit):
            return self._rdiv_units(other)
        return WithUnit(other, self**(-1))

    @cache.lru_cache()
    def __pow__(self, other):
        if self.offset != 0:
            raise TypeError("cannot exponentiate unit with non-zero offset: '%s'" % (self,))
        if isinstance(other, int):
            return Unit(self.names * other,
                        pow(self.factor, other),
                        [p * other for p in self.powers],
                        self.offset,
                        self.lex_names * other)
        if isinstance(other, float):
            inv_exp = 1./other
            rounded = int(floor(inv_exp+0.5))
            if abs(inv_exp - rounded) < 1.e-10:
                return self.__pow__(Fraction(1, rounded))
        if isinstance(other, tuple):
            other = Fraction(*other)
        if isinstance(other, Fraction):
            return Unit(other * self.names,
                        pow(self.factor, other),
                        [p * other for p in self.powers],
                        self.offset,
                        other * self.lex_names)
        raise TypeError("Only integer or rational exponents allowed")

    def isCompatible(self, other):     # added 1998/10/01 GPW
        """
        @param other: another unit
        @type other: L{Unit}
        @returns: C{True} if the units are compatible, i.e. if the powers of
                  the base units are the same
        @rtype: C{bool}
        """
        other = Unit(other)
        return self.powers == other.powers and self.lex_names == other.lex_names

    @cache.lru_cache()
    def conversionFactorTo(self, other):
        """
        @param other: another unit
        @type other: L{Unit}
        @returns: the conversion factor from this unit to another unit
        @rtype: C{float}
        @raises TypeError: if the units are not compatible
        """
        other = Unit(other)
        if not self.isCompatible(other):
            raise TypeError("Incompatible units: '%s', '%s'" % (self, other))
        if self.offset != other.offset and self.factor != other.factor:
            raise TypeError(('Unit conversion (%s to %s) cannot be expressed ' +
                             'as a simple multiplicative factor') % (self, other))
        return float(self.factor / other.factor)

    @cache.lru_cache()
    def conversionTupleTo(self, other): # added 1998/09/29 GPW
        """
        @param other: another unit
        @type other: L{Unit}
        @returns: the conversion factor and offset from this unit to
                  another unit
        @rtype: (C{float}, C{float})
        @raises TypeError: if the units are not compatible
        """
        other = Unit(other)
        if not self.isCompatible(other):
            raise TypeError("Incompatible units: '%s', '%s'" % (self, other))

        # let (s1,d1) be the conversion tuple from 'self' to base units
        #   (ie. (x+d1)*s1 converts a value x from 'self' to base units,
        #   and (x/s1)-d1 converts x from base to 'self' units)
        # and (s2,d2) be the conversion tuple from 'other' to base units
        # then we want to compute the conversion tuple (S,D) from
        #   'self' to 'other' such that (x+D)*S converts x from 'self'
        #   units to 'other' units
        # the formula to convert x from 'self' to 'other' units via the
        #   base units is (by definition of the conversion tuples):
        #     ( ((x+d1)*s1) / s2 ) - d2
        #   = ( (x+d1) * s1/s2) - d2
        #   = ( (x+d1) * s1/s2 ) - (d2*s2/s1) * s1/s2
        #   = ( (x+d1) - (d1*s2/s1) ) * s1/s2
        #   = (x + d1 - d2*s2/s1) * s1/s2
        # thus, D = d1 - d2*s2/s1 and S = s1/s2
        factor = float(self.factor / other.factor)
        offset = float(self.offset - (other.offset * other.factor / self.factor))
        return factor, offset

    def isDimensionless(self):
        return self.is_dimensionless

    def isAngle(self):
        return self.is_angle


def convert(*args):
    """Convert between different units.

    There are two calling conventions:
    - 2 args: >>> convert(Value(1, 'mi'), 'm')
    - 3 args: >>> convert(1, 'mi', 'm')
    The string arguments can also be Unit instances.
    """
    if len(args) == 2:
        val, unit = args
        return val.inUnitsOf(unit)
    elif len(args) == 3:
        val, fromUnit, toUnit = args
        factor, offset = Unit(fromUnit).conversionTupleTo(toUnit)
        return (val + offset) * factor
    raise Exception('Must call convert with 2 or 3 args')


_unit_table = {'': Unit(NumberDict(), Fraction(1), [0]*9, 0)}


class WithDimensionlessUnit(object):
    """
    This is a funny class.  It is designed to be subclassed
    along float, complex, or ndarray.  It provides a simplified
    but compatible API as the WithUnit class, but only works
    for dimensionless quantities.  The reason for this is what
    to do with expressions like:

    4. ns * 5. GHz

    Option 1: Return Value(20, '').  This is consistent, but annoying
    because it won't work directly in contexts that expect a float.
    i.e., sin(5*GHz * 2 * np.pi * 4*ns) raises an exception.  It is
    possible to define a __float__() method, but that doesn't catch all
    cases.

    Option 2: return float(20.0).  This is convenient, but makes
    writing generic code harder because the expected methods and
    properties (._value, .inUnitsOf) don't exist.

    Option 3:
    WithDimensionlessUnit(20.0).  This creates a subclass of float
    that has the necessary methods and properties, but in all other
    ways behaves like a float.

    This implements option 3
    """
    __array_priority__ = 15

    __unit = Unit('') # All instances are dimensionless

    def __new__(cls, value):
        obj = super(WithDimensionlessUnit, cls).__new__(cls, value)
        return obj

    def __reduce__(self):
        return (type(self), (self._value,))

    @property
    def unit(self):
        return self.__unit

    @property
    def _value(self):
        return self._numType(self)

    @property
    def units(self):
        return ''

    def __getitem__(self, idx):
        # getitem with a string tries to do unit conversion.  This is not normally
        # particularly useful with dimensionless numbers, but WithUnits(3, '')['mm/m']
        # will give you 3000.0.  If the index isn't a string, pass to the base class
        # implementation
        if isinstance(idx, (str, Unit)):
            return self._value * self.unit.conversionFactorTo(idx)
        else:
            return super(WithDimensionlessUnit, self).__getitem__(idx)

    def inUnitsOf(self, unit):
        if self.unit.conversionFactorTo(unit) != 1.0:
            raise TypeError("Can't convert dimensionless to %s (scale factor must be 1)" % (unit,))
        else:
            return self

    def inBaseUnits(self):
        return self

    def isDimensionless(self):
        return True

    def isCompatible(self, unit):
        return self.unit.isCompatible(unit)

    def sqrt(self):
        return self.__class__(np.sqrt(self._value))

    # These are a whole bunch of operations to make sure that math
    # between WithDimensionlessUnits and float/complex return
    # the right type.  Without this, DimensionlessValues degrade
    # to float as soon as you do math on them.  Not sure if this is
    # actually a problem.
    def __mul__(self, other):
        result = self._value * other
        return WithUnit(result, '')

    __rmul__ = __mul__

    def __add__(self, other):
        result = self._value + other
        return WithUnit(result, '')

    __radd__ = __add__

    def __div__(self, other):
        result = self._value / other
        return WithUnit(result, '')

    __truediv__ = __div__

    def __rdiv__(self, other):
        result = other / self._value
        return WithUnit(result, '')

    __rtruediv__ = __rdiv__

    def __floordiv__(self, other):
        result = self._value // other
        return WithUnit(result, '')

    def __rfloordiv__(self, other):
        result = other // self._value
        return WithUnit(result, '')

    def __sub__(self, other):
        result = self._value - other
        return WithUnit(result, '')

    def __rsub__(self, other):
        result = other - self._value
        return WithUnit(result, '')

    def __neg__(self):
        result = -self._value
        return WithUnit(result, '')

    def __abs__(self):
        result = abs(self._value)
        return WithUnit(result, '')

    # We need to define all the comparison operators this way so that they
    # work when 'other' is an array type.  This is because we have defined
    # an __array_priority__ flag.  When numpy sees this, it assumes we know
    # how to handle numpy arrays and doesn't handle a NotImplemented return
    # value.  The built in float() operators don't know how to handle arrays
    # so we have to override them.
    
    def __lt__(self, other):
        return self._value < other

    def __le__(self, other):
        return self._value <= other

    def __eq__(self, other):
        return self._value == other

    def __ne__(self, other):
        return self._value != other

    def __ge__(self, other):
        return self._value >= other

    def __gt__(self, other):
        return self._value > other
    
    

class DimensionlessFloat(WithDimensionlessUnit, float):
    _numType = float

    def __iter__(self):
        raise TypeError('DimensionlessFloat not iterable')

WithUnit._dimensionlessTypes[float] = DimensionlessFloat
WithUnit._dimensionlessTypes[int] = DimensionlessFloat
WithUnit._dimensionlessTypes[long] = DimensionlessFloat
WithUnit._dimensionlessTypes[np.float64] = DimensionlessFloat
WithUnit._dimensionlessTypes[np.int64] = DimensionlessFloat
WithUnit._dimensionlessTypes[np.float32] = DimensionlessFloat
WithUnit._numericTypes[DimensionlessFloat] = Value


class DimensionlessComplex(WithDimensionlessUnit, complex):
    _numType = complex

    def __iter__(self):
        raise TypeError('DimensionlessComplex not iterable')

WithUnit._dimensionlessTypes[complex] = DimensionlessComplex
WithUnit._dimensionlessTypes[np.complex128] = DimensionlessComplex
WithUnit._numericTypes[DimensionlessComplex] = Complex


class DimensionlessArray(WithDimensionlessUnit, np.ndarray):
    _numType = staticmethod(np.asarray) # The is a 'copy constructor' used in ._value()

    def __new__(cls, value):
        return (np.array(value)*1.0).view(cls)

    def allclose(self, other, *args, **kw):
        return np.allclose(self, other, *args, **kw)

    def __array_wrap__(self, obj):
        '''
        This function is called at the end of uops and similar functions.
        ndarray has some weird logic where reductions like sum() that result
        in zero-rank arrays automatically convert to numpy scalars
        if-and-only-if the type is a ndarray base class.  If we want the same
        we have to do it here
        '''
        if obj.shape == ():
            return WithUnit(obj[()], '')
        else:
            return np.ndarray.__array_wrap__(self, obj)

WithUnit._dimensionlessTypes[np.ndarray] = DimensionlessArray
WithUnit._dimensionlessTypes[list] = DimensionlessArray
WithUnit._numericTypes[DimensionlessArray] = ValueArray


# SI unit definitions
def _addUnit(name, factor, unit, comment='', label='', prefixable=False):
    if name in _unit_table:
        raise KeyError('Unit %s already defined' % name)
    if comment:
        _help.append((name, comment, label, prefixable))
    base = globals()[name] = _unit_table[name] = Unit(name, factor, unit)
    if prefixable:
        for prefix, factor in _prefixes:
            if (prefix + name) in _unit_table:
                raise KeyError('Unit %s already defined' % name)
            unit = Unit(prefix + name, factor, base)
            globals()[prefix + name] = _unit_table[prefix + name] = unit


def addNonSI(name, prefixable=False):
    base = Unit(name, Fraction(1), [0,0,0,0,0,0,0,0,0], lex_names=name)
    base.name # This forces the Lazy evaluation of name, which populates _unit_table
    if prefixable:
        for prefix, factor in _prefixes:
            if (prefix + name) in _unit_table:
                raise KeyError('Unit %s%s already defined' % (prefix, name))
            derived = Unit(prefix+name, factor, base)
            derived.name


_help = []

# SI prefixes
_prefixes = [
    ('Y',  Fraction(10**24)),
    ('Z',  Fraction(10**23)),
    ('E',  Fraction(10**18)),
    ('P',  Fraction(10**15)),
    ('T',  Fraction(10**12)),
    ('G',  Fraction(10**9)),
    ('M',  Fraction(10**6)),
    ('k',  Fraction(10**3)),
    ('h',  Fraction(10**2)),
    ('da', Fraction(10**1)),
    ('d',  Fraction(1, 10**1)),
    ('c',  Fraction(1, 10**2)),
    ('m',  Fraction(1, 10**3)),
    ('u',  Fraction(1, 10**6)),
    ('n',  Fraction(1, 10**9)),
    ('p',  Fraction(1, 10**12)),
    ('f',  Fraction(1, 10**15)),
    ('a',  Fraction(1, 10**18)),
    ('z',  Fraction(1, 10**21)),
    ('y',  Fraction(1, 10**24))
    ]
# SI prefixes
"""
_prefixes = [
    ('Y',  1.e24),
    ('Z',  1.e21),
    ('E',  1.e18),
    ('P',  1.e15),
    ('T',  1.e12),
    ('G',  1.e9),
    ('M',  1.e6),
    ('k',  1.e3),
    ('h',  1.e2),
    ('da', 1.e1),
    ('d',  1.e-1),
    ('c',  1.e-2),
    ('m',  1.e-3),
    ('u',  1.e-6),
    ('n',  1.e-9),
    ('p',  1.e-12),
    ('f',  1.e-15),
    ('a',  1.e-18),
    ('z',  1.e-21),
    ('y',  1.e-24),
    ]
"""
_help.append('SI prefixes:' +
    ', '.join(prefix + ' (%.0E)' % value for prefix, value in _prefixes))


# SI base units
_help.append('SI base units:')

_addUnit('m',   Fraction(1),      [1,0,0,0,0,0,0,0,0], 'meter',     prefixable=True)
_addUnit('g',   Fraction(1,1000), [0,1,0,0,0,0,0,0,0], 'gram',      prefixable=True)
_addUnit('s',   Fraction(1),      [0,0,1,0,0,0,0,0,0], 'second',    prefixable=True)
_addUnit('A',   Fraction(1),      [0,0,0,1,0,0,0,0,0], 'Ampere',    prefixable=True)
_addUnit('K',   Fraction(1),      [0,0,0,0,1,0,0,0,0], 'Kelvin',    prefixable=True)
_addUnit('mol', Fraction(1),      [0,0,0,0,0,1,0,0,0], 'mole',      prefixable=True)
_addUnit('cd',  Fraction(1),      [0,0,0,0,0,0,1,0,0], 'candela',   prefixable=True)
_addUnit('rad', Fraction(1),      [0,0,0,0,0,0,0,1,0], 'radian',    prefixable=True)
_addUnit('sr',  Fraction(1),      [0,0,0,0,0,0,0,0,1], 'steradian', prefixable=True)

_base_names = ['m', 'kg', 's', 'A', 'K', 'mol', 'cd', 'rad', 'sr']


# SI derived units; these automatically get prefixes
_help.append('SI derived units:')

_addUnit('Hz',  Fraction(1),  s**-1,     'Hertz',     '1/s',      prefixable=True)
_addUnit('N',   Fraction(1),  m*kg/s**2, 'Newton',    'm*kg/s^2', prefixable=True)
_addUnit('Pa',  Fraction(1),  N/m**2,    'Pascal',    'N/m^2',    prefixable=True)
_addUnit('J',   Fraction(1),  N*m,       'Joule',     'N*m',      prefixable=True)
_addUnit('W',   Fraction(1),  J/s,       'Watt',      'J/s',      prefixable=True)
_addUnit('C',   Fraction(1),  s*A,       'Coulomb',   's*A',      prefixable=True)
_addUnit('V',   Fraction(1),  W/A,       'Volt',      'W/A',      prefixable=True)
_addUnit('F',   Fraction(1),  C/V,       'Farad',     'C/V',      prefixable=True)
_addUnit('Ohm', Fraction(1),  V/A,       'Ohm',       'V/A',      prefixable=True)
_addUnit('S',   Fraction(1),  A/V,       'Siemens',   'A/V',      prefixable=True)
_addUnit('Wb',  Fraction(1),  V*s,       'Weber',     'V*s',      prefixable=True)
_addUnit('T',   Fraction(1),  Wb/m**2,   'Tesla',     'Wb/m^2',   prefixable=True)
_addUnit('gauss',Fraction(1,10000),T,   'gauss',     '1e-4 T',   prefixable=True)
_addUnit('H',   Fraction(1),  Wb/A,      'Henry',     'Wb/A',     prefixable=True)
_addUnit('lm',  Fraction(1),  cd*sr,     'Lumen',     'cd*sr',    prefixable=True)
_addUnit('lx',  Fraction(1),  lm/m**2,   'Lux',       'lm/m^2',   prefixable=True)
_addUnit('Bq',  Fraction(1),  s**-1,     'Becquerel', '1/s',      prefixable=True)


# Time units
_help.append('Time units:')

_addUnit('min', 60.,     s,   'minute', '60*s')
_addUnit('h',   60.,     min, 'hour',   '60*min')
_addUnit('d',   24.,     h,   'day',    '24*h')
_addUnit('y',   365.25, d,   'year',   '365.25*d')

# Length units
_help.append('Length units:')

_addUnit('inch', 2.54, cm,   'inch', '2.54*cm')
_addUnit('ft',   12.,   inch, 'foot', '12*inch')
_addUnit('mi',   5280, ft,   'mile', '5280*ft')

# Area units
_help.append('Area units:')

_addUnit('acre', 1./640., mi**2, 'acre', '1/640*mi^2')

# Volume units
_help.append('Volume units:')

_addUnit('l',  Fraction(1),  dm**3, 'liter', 'dm^3')
_addUnit('dl', Fraction(1,10),   l, 'deci liter', '0.1 l')
_addUnit('cl', Fraction(1,100),  l, 'centi liter', '0.01 l')
_addUnit('ml', Fraction(1,1000), l, 'milli liter', '0.001 l')

# Force units
_help.append('Force units:')

_addUnit('dyn', 1.e-5, N, 'dyne (cgs unit)', '10^-5 N')

# Energy units
_help.append('Energy units:')

_addUnit('erg', Fraction(1, 10**7), J, 'erg (cgs unit)', '10^-7 J')
_addUnit('cal', 4.184, J, 'calorie', '4.184 J')
_addUnit('kcal', 1000., cal, 'kilocalorie', '1000 cal')
_addUnit('Btu', 1055.05585262, J, 'British thermal unit', '1055.05585262 J')
_addUnit('eV', 1.602176565e-19, C*V, 'electron volt', '1.602176565*10^19 C*V',
         prefixable=True)

# Power units
_help.append('Power units:')

_addUnit('hp', 745.7, W, 'horsepower', '745.7 W')

# Pressure units
_help.append('Pressure units:')

_addUnit('bar', Fraction(10**5), Pa, 'bar (cgs unit)', '10^5 Pa')
_addUnit('atm', 101325., Pa, 'standard atmosphere', '101325 Pa')
_addUnit('torr', 1./760., atm, 'torr = mm of mercury', '1/760 atm')

# Angle units
_help.append('Angle units:')

_addUnit('deg', pi/180, 'rad', 'degrees', 'pi/180 rad')

# Temperature units
_help.append('Temperature units:')

_addUnit('degC', 1.0, Unit({}, 1.0, K.powers, 273.15), 'degrees Celcius')
_addUnit('degF', 1.0, Unit({}, 5./9., K.powers, 459.67), 'degrees Fahrenheit')


# Constants


c       = 299792458.*m/s                   # speed of light
ly      = 1.*c*y                           # light year
mu0     = 4.e-7*pi*N/A**2                  # permeability of vacuum
eps0    = 1/mu0/c**2                       # permittivity of vacuum
G       = 6.67259e-11*m**3/kg/s**2         # gravitational constant
hplanck = 6.62606957e-34*J*s               # Planck constant
hbar    = hplanck/(2*pi)                   # Planck constant / 2pi
e       = 1.60217733e-19*C                 # elementary charge
me      = 9.1093897e-31*kg                 # electron mass
mp      = 1.6726231e-27*kg                 # proton mass
Nav     = 6.0221367e23/mol                 # Avogadro number
k       = 1.380658e-23*J/K                 # Boltzmann constant
wk      = 7*d                              # week
yd      = 3*ft                             # yard
nmi     = 1852.*m                          # Nautical mile
Ang     = 1.e-10*m                         # Angstrom
lyr     = c*y                              # light year
Bohr    = 4*pi*eps0*hbar**2/me/e**2        # Bohr radius
ha      = 10000*m**2                       # hectare
b       = 1.e-28*m                         # barn
Hartree = me*e**4/16/pi**2/eps0**2/hbar**2 # Wavenumbers/inverse cm
rootHz  = sqrtHz = Hz**0.5                 # for power spectral density
tsp     = 4.92892159375*ml   # teaspoon
tbsp    = 3*tsp              # tablespoon
floz    = 2*tbsp             # fluid ounce
cup     = 8*floz             # cup
pint    = 16*floz            # pint
qt      = 2*pint             # quart
galUS   = 4*qt               # US gallon
galUK   = 4.54609*l          # British gallon
amu     = 1.6605402e-27*kg   # atomic mass units
oz      = 28.349523125*g     # ounce
lb      = 16*oz              # pound
ton     = 2000*lb            # ton
Ken     = k*K                # Kelvin as energy unit
cali    = 4.1868*J           # international calorie
kcali   = 1000*cali          # international kilocalorie
psi     = 6894.75729317*Pa   # pounds per square inch
degR    = (5./9.)*K          # degrees Rankine
bohr_magneton = 9.2740096820e-24 * J/T # Bohr magneton

_addUnit('phi0', 1.0, hplanck/(2*e), prefixable=True)

# some common textual units (no conversions here)
dB = Unit('dB')
dBm = Unit('dBm')

def description():
    """Return a string describing all available units."""
    s = ''  # collector for description text
    for entry in _help:
        if isinstance(entry, str):
            # headline for new section
            s += '\n' + entry + '\n'
        elif isinstance(entry, tuple):
            name, comment, unit, prefixable = entry
            prefix = '*' if prefixable else ''
            s += '%-8s  %-26s %s\n' % (prefix + name, comment, unit)
        else:
            # impossible
            raise TypeError, 'wrong construction of _help list'
    return s

# add the description of the units to the module's doc string:
__doc__ += '\n' + description()


if __name__ == '__main__':
    # some very basic demonstration code

    l = WithUnit(10., 'm')
    big_l = WithUnit(10., 'km')
    print big_l + l
    t = WithUnit(314159., 's')

    e = 2.7 * Hartree * Nav
    print e.inUnitsOf('kcal/mol')
    print e.inBaseUnits()

    freeze = 0 * Unit('degC')
    print freeze['degF']
