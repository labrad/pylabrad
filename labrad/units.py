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

from math import floor, pi
#try:
#    from numpy import array, ndarray
#    useNumpy = True
#except ImportError:
#    array = ndarray = None
#    useNumpy = False

from labrad import grammar
from labrad.ratio import Ratio


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


class WithUnit(object):
    """Mixin class for adding units to numeric types."""

    def __new__(cls, value, unit=None):
        #if unit is None:
        #    return 1.0 * value # make sure return value is at least a float
        cls = cls._findClass(type(value), unit)
        
        inst = super(WithUnit, cls).__new__(cls, value)
        inst.unit = Unit(unit)
        return inst
        
    _numericTypes = {}
        
    @classmethod
    def _findClass(cls, numType, unit):
        """Find a class for a particular numeric type and unit.
        
        Classes will be created if they haven't been already.
        """
        # find class with units for this numeric type
        try:
            cls = cls._numericTypes[numType]
        except KeyError:
            raise TypeError('Cannot use units with instances of type %s' % (numType,))
        return cls
        
    @property
    def value(self):
        return self.__class__._numType(self)

    @property
    def units(self):
        """A string representation of the unit of this value."""
        if self.unit is None:
            return ''
        return self.unit.name

    def __str__(self):
        if self.unit is None:
            return str(self.value)
        return '%s %s' % (self.value, self.unit)

    def __repr__(self):
        if self.unit is None:
            return '%s(%r, None)' % (self.__class__.__name__, self.value)
        return '%s(%r, %r)' % (self.__class__.__name__, self.value, self.unit.name)

    def _sum(self, other, sign1, sign2):
        if isinstance(other, WithUnit):
            if other.unit is not None:
                factor = other.unit.conversionFactorTo(self.unit)
            else:
                factor = 1
            value = sign1 * self.value + sign2 * other.value * factor
        else:
            value = sign1 * self.value + sign2 * other
        return WithUnit(value, self.unit)

    def __add__(self, other):
        return self._sum(other, 1, 1)

    __radd__ = __add__

    def __sub__(self, other):
        return self._sum(other, 1, -1)

    def __rsub__(self, other):
        return self._sum(other, -1, 1)

    def __eq__(self, other):
        if not isinstance(other, WithUnit):
            if self.unit is None:
                return self.value == other
            return False
        return self.__cmp__(other) == 0

    def __ne__(self, other):
        return not self.__eq__(other)

    def __cmp__(self, other):
        diff = self._sum(other, 1, -1)
        return cmp(diff.value, 0)
        
    def __mul__(self, other):
        if isinstance(other, Unit):
            return WithUnit(self.value, self.unit * other)
        if isinstance(other, WithUnit):
            if self.unit is None:
                return WithUnit(self.value * other.value, other.unit)
            if other.unit is None:
                return WithUnit(self.value * other.value, self.unit)
            return WithUnit(self.value * other.value,
                            self.unit * other.unit)
        return WithUnit(self.value * other, self.unit)

    __rmul__ = __mul__

    def __div__(self, other):
        if isinstance(other, Unit):
            return WithUnit(self.value, self.unit / other)
        if isinstance(other, WithUnit):
            if self.unit is None and other.unit is None:
                return WithUnit(self.value / other.value, None)
            if self.unit is None:
                return WithUnit(self.value / other.value, pow(other.unit, -1))
            if other.unit is None:
                return WithUnit(self.value / other.value, self.unit)
            return WithUnit(self.value / other.value,
                            self.unit / other.unit)
        return WithUnit(self.value / other, self.unit)
        
    def __rdiv__(self, other):
        if isinstance(other, Unit):
            return WithUnit(self.value, other / self.unit)
        if isinstance(other, WithUnit):
            if self.unit is None and other.unit is None:
                return WithUnit(other.value / self.value, None)
            if self.unit is None:
                return WithUnit(other.value / self.value, other.unit)
            if other.unit is None:
                return WithUnit(other.value / self.value, pow(self.unit, -1))
            return WithUnit(other.value / self.value,
                            other.unit / self.unit)
        return WithUnit(other / self.value, pow(self.unit, -1))

    def __pow__(self, other):
        if isinstance(other, (WithUnit, Unit)) and not other.isDimensionless():
            raise TypeError('Exponents must be dimensionless')
        if self.unit is None:
            return WithUnit(pow(self.value, float(other)), None)
        return WithUnit(pow(self.value, float(other)),
                        pow(self.unit, other))

    def __rpow__(self, other):
        if not self.isDimensionless():
            raise TypeError('Exponents must be dimensionless')
        if self.unit is None:
            return pow(other, self.value)
        return pow(other, self.value * self.unit.factor)

    def __abs__(self):
        return WithUnit(abs(self.value), self.unit)

    def __pos__(self):
        return self

    def __neg__(self):
        return WithUnit(-self.value, self.unit)

    def __nonzero__(self):
        return self.value != 0

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
        if self.unit is None:
            return WithUnit(self.value, unit)
        factor, offset = self.unit.conversionTupleTo(unit)
        return WithUnit((self.value + offset) * factor, unit)

    # Contributed by Berthold Hoellmann
    def inBaseUnits(self):
        """
        @returns: the same quantity converted to base units,
        i.e. SI units in most cases
        @rtype: L{PhysicalQuantity}
        """
        if self.unit is None:
            return self
        num = ''
        denom = ''
        for unit, power in (zip(_base_names, self.unit.powers) +
                            self.unit.lex_names.items()):
            if power != 1 and power != -1:
                unit += '**' + str(abs(power))
            if power < 0: denom += '/' + unit
            elif power > 0: num += '*' + unit
        if not len(num):
            num = '1'
        else:
            num = num[1:] # strip leading '*'
        name = num + denom
        if name == '1':
            name = ''
        return WithUnit(self.value * self.unit.factor, name)

    def isCompatible(self, unit):
        """
        @param unit: a unit
        @type unit: C{str}
        @returns: C{True} if the specified unit is compatible with the
        one of the quantity
        @rtype: C{bool}
        """
        if self.unit is None:
            return True
        return self.unit.isCompatible(unit)
        
    def isDimensionless(self):
        if self.unit is None:
            return True
        return self.unit.isDimensionless()
        
    def sqrt(self):
        return pow(self, Ratio(1,2))

class Value(WithUnit, float):
    _numType = float
    def __getitem__(self, unit):
        """Return value of physical quantity expressed in new units."""
        return self.inUnitsOf(unit).value
    def __iter__(self):
        raise TypeError("'Value' object is not iterable")
WithUnit._numericTypes[float] = Value
WithUnit._numericTypes[int] = Value
WithUnit._numericTypes[long] = Value

class Complex(WithUnit, complex):
    _numType = complex
    def __getitem__(self, unit):
        """Return value of physical quantity expressed in new units."""
        return self.inUnitsOf(unit).value
    def __iter__(self):
        raise TypeError("'Complex' object is not iterable")
WithUnit._numericTypes[complex] = Complex

# add support for numeric types returned by most numpy/scipy functions
try:
    import numpy
    WithUnit._numericTypes[numpy.float64] = Value
    WithUnit._numericTypes[numpy.complex128] = Complex
except ImportError:
    pass

#if useNumpy:
#    class ValueArray(WithUnit, ndarray):
#        _numType = ndarray
#        _units = {}
#    WithUnit._numericTypes[ndarray] = ValueArray
#    WithUnit._numericTypes[list] = ValueArray


class Unit(object):
    """Unit of measurement

    A unit is defined by a name (possibly composite), a scaling factor,
    and the exponentials of each of the SI base units that enter into
    it. Units can be multiplied, divided, and raised to rational powers.
    """
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
            elif unit is None:
                return None
            raise Exception('Cannot create Unit for %r' % unit)
        elif len(args) == 3 and isinstance(args[2], (Unit, WithUnit, str)):
            # construct a named unit that is equal to a
            # previously-defined unit, times a factor
            name, factor, unit = args[:3]
            if isinstance(unit, WithUnit):
                unit, factor = unit.unit, factor * unit.value
            elif isinstance(unit, str):
                unit = cls._parse(unit)
            inst = Unit(name, factor * unit.factor,
                        unit.powers, unit.offset)
            return inst
        # construct a new unit 
        inst = super(Unit, cls).__new__(cls)
        inst._init(*args, **kw)
        return inst
        
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
                    unit = unit * _unit_table[term]**(sign*Ratio(num, denom))
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
        return Unit(NumberDict(), 1., [0]*9, 0, name)
    
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
            self.names[names] = Ratio(1)
        else:
            self.names = names
        self.factor = factor
        self.offset = offset
        self.powers = [Ratio(p) for p in powers]
        if isinstance(lex_names, str):
            self.lex_names = NumberDict()
            if lex_names:
                self.lex_names[lex_names] = Ratio(1)
        else:
            self.lex_names = lex_names
            
    @property
    def name(self):
        if hasattr(self, '_name'):
            return self._name
        num = ''
        denom = ''
        full_dict = dict(self.names, **self.lex_names)
        for unit, power in full_dict.items():
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
            return (self.powers == other.powers and
                    self.lex_names == other.lex_names)
        return False
        
    def __ne__(self, other):
        return not self.__eq__(other)
        
    def __mul__(self, other):
        if other is None:
            return self
        elif isinstance(other, Unit):
            if self.offset != 0 or other.offset != 0:
                raise TypeError("cannot multiply units with non-zero offset: '%s', '%s'" % (self, other))
            return Unit(self.names + other.names,
                        self.factor * other.factor,
                        [a + b for a, b in zip(self.powers, other.powers)],
                        self.offset,
                        self.lex_names + other.lex_names)
        return WithUnit(other, self)

    __rmul__ = __mul__

    def __div__(self, other):
        if other is None:
            if self.offset != 0:
                raise TypeError("cannot divide unit with non-zero offset: '%s'" % (self,))
            return self
        elif isinstance(other, Unit):
            if self.offset != 0 or other.offset != 0:
                raise TypeError("cannot divide units with non-zero offset: '%s', '%s'" % (self, other))
            return Unit(self.names - other.names,
                        self.factor / other.factor,
                        [a - b for a, b in zip(self.powers, other.powers)],
                        self.offset,
                        self.lex_names - other.lex_names)
        return WithUnit(1.0 / other, self)

    def __rdiv__(self, other):
        if other is None:
            if self.offset != 0:
                raise TypeError("cannot divide unit with non-zero offset: '%s'" % (self,))
            return Unit(NumberDict() - self.names,
                        1.0 / self.factor,
                        [- b for b in self.powers],
                        self.offset,
                        NumberDict() - self.lex_names)
        if isinstance(other, Unit):
            if self.offset != 0 or other.offset != 0:
                raise TypeError("cannot divide units with non-zero offset: '%s', '%s'" % (self, other))
            return Unit(other.names - self.names,
                        other.factor / self.factor,
                        [a - b for a, b in zip(other.powers, self.powers)],
                        self.offset,
                        other.lex_names - self.lex_names)
        return WithUnit(other, self**(-1))

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
                return self.__pow__(Ratio(1, rounded))
        if isinstance(other, tuple):
            other = Ratio(*other)
        if isinstance(other, Ratio):
            return Unit(other * self.names,
                        pow(self.factor, float(other)),
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
        if other is None:
            return self.factor
        if self.offset != other.offset and self.factor != other.factor:
            raise TypeError(('Unit conversion (%s to %s) cannot be expressed ' +
                             'as a simple multiplicative factor') % (self, other))
        return self.factor / other.factor

    def conversionTupleTo(self, other): # added 1998/09/29 GPW
        """
        @param other: another unit
        @type other: L{Unit}
        @returns: the conversion factor and offset from this unit to
                  another unit
        @rtype: (C{float}, C{float})
        @raises TypeError: if the units are not compatible
        """
        if other is None:
            return 1.0, 0.0
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
        factor = self.factor / other.factor
        offset = self.offset - (other.offset * other.factor / self.factor)
        return factor, offset

    def isDimensionless(self):
        return not any(self.powers) and not any(self.lex_names.values())

    def isAngle(self):
        return (self.powers[7] == 1 and
                sum(self.powers) == 1 and
                not any(self.lex_names.values())) 


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


_unit_table = {'': Unit(NumberDict(), 1., [0]*9, 0)}


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

_help = []

# SI prefixes
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

_help.append('SI prefixes:' +
    ', '.join(prefix + ' (%.0E)' % value for prefix, value in _prefixes))


# SI base units
_help.append('SI base units:')

_addUnit('m',   1.,    [1,0,0,0,0,0,0,0,0], 'meter',     prefixable=True)
_addUnit('g',   0.001, [0,1,0,0,0,0,0,0,0], 'gram',      prefixable=True)
_addUnit('s',   1.,    [0,0,1,0,0,0,0,0,0], 'second',    prefixable=True)
_addUnit('A',   1.,    [0,0,0,1,0,0,0,0,0], 'Ampere',    prefixable=True)
_addUnit('K',   1.,    [0,0,0,0,1,0,0,0,0], 'Kelvin',    prefixable=True)
_addUnit('mol', 1.,    [0,0,0,0,0,1,0,0,0], 'mole',      prefixable=True)
_addUnit('cd',  1.,    [0,0,0,0,0,0,1,0,0], 'candela',   prefixable=True)
_addUnit('rad', 1.,    [0,0,0,0,0,0,0,1,0], 'radian',    prefixable=True)
_addUnit('sr',  1.,    [0,0,0,0,0,0,0,0,1], 'steradian', prefixable=True)

_base_names = ['m', 'kg', 's', 'A', 'K', 'mol', 'cd', 'rad', 'sr']

    
# SI derived units; these automatically get prefixes
_help.append('SI derived units:')

_addUnit('Hz',  1.0,  s**-1,     'Hertz',     '1/s',      prefixable=True)
_addUnit('N',   1.0,  m*kg/s**2, 'Newton',    'm*kg/s^2', prefixable=True)
_addUnit('Pa',  1.0,  N/m**2,    'Pascal',    'N/m^2',    prefixable=True)
_addUnit('J',   1.0,  N*m,       'Joule',     'N*m',      prefixable=True)
_addUnit('W',   1.0,  J/s,       'Watt',      'J/s',      prefixable=True)
_addUnit('C',   1.0,  s*A,       'Coulomb',   's*A',      prefixable=True)
_addUnit('V',   1.0,  W/A,       'Volt',      'W/A',      prefixable=True)
_addUnit('F',   1.0,  C/V,       'Farad',     'C/V',      prefixable=True)
_addUnit('Ohm', 1.0,  V/A,       'Ohm',       'V/A',      prefixable=True)
_addUnit('S',   1.0,  A/V,       'Siemens',   'A/V',      prefixable=True)
_addUnit('Wb',  1.0,  V*s,       'Weber',     'V*s',      prefixable=True)
_addUnit('T',   1.0,  Wb/m**2,   'Tesla',     'Wb/m^2',   prefixable=True)
_addUnit('H',   1.0,  Wb/A,      'Henry',     'Wb/A',     prefixable=True)
_addUnit('lm',  1.0,  cd*sr,     'Lumen',     'cd*sr',    prefixable=True)
_addUnit('lx',  1.0,  lm/m**2,   'Lux',       'lm/m^2',   prefixable=True)
_addUnit('Bq',  1.0,  s**-1,     'Becquerel', '1/s',      prefixable=True)


# Time units
_help.append('Time units:')

_addUnit('min', 60,     s,   'minute', '60*s')
_addUnit('h',   60,     min, 'hour',   '60*min')
_addUnit('d',   24,     h,   'day',    '24*h')
_addUnit('y',   365.25, d,   'year',   '365.25*d')

# Length units
_help.append('Length units:')

_addUnit('inch', 2.54, cm,   'inch', '2.54*cm')
_addUnit('ft',   12,   inch, 'foot', '12*inch')
_addUnit('mi',   5280, ft,   'mile', '5280*ft')

# Area units
_help.append('Area units:')

_addUnit('acre', 1./640., mi**2, 'acre', '1/640*mi^2')

# Volume units
_help.append('Volume units:')

_addUnit('l',  1.0, dm**3, 'liter', 'dm^3')
_addUnit('dl', 0.1, l, 'deci liter', '0.1 l')
_addUnit('cl', 0.01, l, 'centi liter', '0.01 l')
_addUnit('ml', 0.001, l, 'milli liter', '0.001 l')

# Force units
_help.append('Force units:')

_addUnit('dyn', 1.e-5, N, 'dyne (cgs unit)', '10^-5 N')

# Energy units
_help.append('Energy units:')

_addUnit('erg', 1.e-7, J, 'erg (cgs unit)', '10^-7 J')
_addUnit('cal', 4.184, J, 'calorie', '4.184 J')
_addUnit('kcal', 1000, cal, 'kilocalorie', '1000 cal')
_addUnit('Btu', 1055.05585262, J, 'British thermal unit', '1055.05585262 J')
_addUnit('eV', 1.6022e-19, C*V, 'electron volt', '1.6022*10^19 C*V',
         prefixable=True)

# Power units
_help.append('Power units:')

_addUnit('hp', 745.7, W, 'horsepower', '745.7 W')

# Pressure units
_help.append('Pressure units:')

_addUnit('bar', 1.e5, Pa, 'bar (cgs unit)', '10^5 Pa')
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
hplanck = 6.6260755e-34*J*s                # Planck constant
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
