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
#

"""
Physical quantities with units.

This module provides a data type that represents a physical
quantity together with its unit. It is possible to add and
subtract these quantities if the units are compatible, and
a quantity can be converted to another compatible unit.
Multiplication, subtraction, and raising to integer powers
is allowed without restriction, and the result will have
the correct unit. A quantity can be raised to a non-integer
power only if the result can be represented by integer powers
of the base units.

The values of physical constants are taken from the 1986
recommended values from CODATA. Other conversion factors
(e.g. for British units) come from various sources. I can't
guarantee for the correctness of all entries in the unit
table, so use this at your own risk.

This module is originally from the ScientificPython package.
The version included with LabRAD has been slightly changed:

    - removed depency on numpy or numeric
    - included NumberDict so the module is self-contained
    - units that cannot be converted to SI are kept as text alone
    - PhysicalQuantity types are derived from numeric types, and a unit
      mixin.  Hence, they can be treated directly as numbers
    - PhysicalQuantity defines a __getitem__ method to
      express the value in a new unit, e.g:
      >>> PQ(1, 'GHz')['Hz'] -> 1e9
      
"""

from math import floor, ceil, pi

from labrad import grammar
from labrad.util.ratio import Ratio


# Dictionary containing numbers
#
# These objects are meant to be used like arrays with generalized
# indices. Non-existent elements default to zero. Global operations
# are addition, subtraction, and multiplication/division by a scalar.
#
# Written by Konrad Hinsen <hinsen@cnrs-orleans.fr>
# last revision: 2006-10-16
#

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


class HasUnits(object):
    def __new__(cls, value, unit=None):
        if unit is None:
            return value
        inst = super(HasUnits, cls).__new__(cls, value)
        inst.unit = _findUnit(unit)
        return inst

    @property
    def value(self):
        return self._numType(self)

    @property
    def units(self):
        return self.unit.labradName()

    def __str__(self):
        return str(self.value) + ' ' + self.unit.name()

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__,
                               self.value, self.unit.name())

    def _sum(self, other, sign1, sign2):
        if isinstance(other, HasUnits):
            new_value = sign1 * self.value + \
                        sign2 * other.value * other.unit.conversionFactorTo(self.unit)
        else:
            new_value = sign1 * self.value + sign2 * other
        return withUnits(new_value, self.unit)

    def __add__(self, other):
        return self._sum(other, 1, 1)

    __radd__ = __add__

    def __sub__(self, other):
        return self._sum(other, 1, -1)

    def __rsub__(self, other):
        return self._sum(other, -1, 1)

    def __cmp__(self, other):
        diff = self._sum(other, 1, -1)
        return cmp(diff.value, 0)

    def __mul__(self, other):
        if not isinstance(other, HasUnits):
            return withUnits(self.value * other, self.unit)
        value = self.value * other.value
        unit = self.unit * other.unit
        if unit.isDimensionless():
            return value * unit.factor
        else:
            return withUnits(value, unit)

    __rmul__ = __mul__

    def __div__(self, other):
        if not isinstance(other, HasUnits):
            return withUnits(self.value / other, self.unit)
        value = self.value / other.value
        unit = self.unit / other.unit
        if unit.isDimensionless():
            return value * unit.factor
        else:
            return withUnits(value, unit)

    def __rdiv__(self, other):
        if not isinstance(other, HasUnits):
            return withUnits(other / self.value, pow(self.unit, -1))
        value = other.value / self.value
        unit = other.unit / self.unit
        if unit.isDimensionless():
            return value * unit.factor
        else:
            return withUnits(value, unit)

    def __pow__(self, other):
        if isinstance(other, HasUnits):
            raise TypeError('Exponents must be dimensionless')
        if isinstance(other, Ratio):
            return withUnits(pow(self.value, float(other)),
                             pow(self.unit, other))
        else:
            return withUnits(pow(self.value, other),
                             pow(self.unit, other))

    def __rpow__(self, other):
        raise TypeError('Exponents must be dimensionless')

    def __abs__(self):
        return withUnits(abs(self.value), self.unit)

    def __pos__(self):
        return self

    def __neg__(self):
        return withUnits(-self.value, self.unit)

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
        value = _convertValue(self.value, self.unit, unit)
        return withUnits(value, unit)

    # Contributed by Berthold Hoellmann
    def inBaseUnits(self):
        """
        @returns: the same quantity converted to base units,
        i.e. SI units in most cases
        @rtype: L{PhysicalQuantity}
        """
        new_value = self.value * self.unit.factor
        num = ''
        denom = ''
        for unit, power in zip(_base_names, self.unit.powers):
            if power < 0:
                denom += '/' + unit
                if power != -1:
                    denom += '**' + str(-power)
            elif power > 0:
                num += '*' + unit
                if power != 1:
                    num += '**' + str(power)
        for unit, power in self.unit.lex_names.items():
            if power < 0:
                denom += '/' + unit
                if power != -1:
                    denom += '**' + str(-power)
            elif power > 0:
                num += '*' + unit
                if power != 1:
                    num += '**' + str(power)
        if len(num) == 0:
            num = '1'
        else:
            num = num[1:] # strip leading '*'
        name = num + denom
        if name == '1':
            name = ''
        return withUnits(new_value, name)

    def isCompatible(self, unit):
        """
        @param unit: a unit
        @type unit: C{str}
        @returns: C{True} if the specified unit is compatible with the
        one of the quantity
        @rtype: C{bool}
        """
        unit = _findUnit(unit)
        return self.unit.isCompatible(unit)

    def getValue(self):
        """Return value of physical quantity (no unit)."""
        return self.value

    def getUnitName(self):
        """Return unit (string) of physical quantity."""
        return self.unit.name()

    def sqrt(self):
        return pow(self, Ratio(1,2))
    
    def __getitem__(self, newUnit):
        """Return value of physical quantity expressed in new units."""
        if isinstance(newUnit, HasUnits):
            newUnit = newUnit.unit
        return self.inUnitsOf(newUnit).getValue()

class Value(HasUnits, float):
    _numType = float

class Complex(HasUnits, complex):
    _numType = complex

_classDict = {float: Value, complex: Complex}

def withUnits(value, unit=None):
    t = type(1.0 * value)
    if t not in _classDict:
        valueType = type('%sWithUnits' % t.__name__,
                         (HasUnits, t), {'_numType': t})
        _classDict[t] = valueType
    cls = _classDict[t]
    return cls(value, unit)


class Unit(object):

    """
    Unit of measurement

    A unit is defined by a name (possibly composite), a scaling factor,
    and the exponentials of each of the SI base units that enter into
    it. Units can be multiplied, divided, and raised to rational powers.
    """

    def __init__(self, names, factor, powers, offset=0, lex_names=''):
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
        if isinstance(names, basestring):
            self.names = NumberDict()
            self.names[names] = Ratio(1)
        else:
            self.names = names
        self.factor = factor
        self.offset = offset
        self.powers = [Ratio(p) for p in powers]
        if isinstance(lex_names, basestring):
            self.lex_names = NumberDict()
            if lex_names:
                self.lex_names[lex_names] = Ratio(1)
        else:
            self.lex_names = lex_names

    def __repr__(self):
        return '<Unit %s>' % self.name()

    __str__ = __repr__

    def __cmp__(self, other):
        if not isinstance(other, HasUnits):
            return cmp(self.factor, other)
        if self.powers != other.powers or self.lex_names != other.lex_names:
            raise TypeError('Incompatible units')
        return cmp(self.factor, other.factor)

    def __mul__(self, other):
        if self.offset != 0 or (isinstance(other, Unit) and other.offset != 0):
            raise TypeError("cannot multiply units with non-zero offset")
        if isinstance(other, Unit):
            return Unit(self.names + other.names,
                        self.factor * other.factor,
                        [a + b for a, b in zip(self.powers, other.powers)],
                        self.offset,
                        self.lex_names + other.lex_names)
        else:
            return Unit(self.names + {str(other): Ratio(1)},
                        self.factor * other,
                        self.powers,
                        self.offset,
                        self.lex_names)

    __rmul__ = __mul__

    def __div__(self, other):
        if self.offset != 0 or (isinstance(other, Unit) and other.offset != 0):
            raise TypeError("cannot divide units with non-zero offset")
        if isinstance(other, Unit):
            return Unit(self.names - other.names,
                        self.factor / other.factor,
                        [a - b for a, b in zip(self.powers, other.powers)],
                        self.offset,
                        self.lex_names - other.lex_names)
        else:
            return Unit(self.names + {str(other): Ratio(-1)},
                        self.factor / other,
                        self.powers,
                        self.offset,
                        self.lex_names)

    def __rdiv__(self, other):
        if self.offset != 0 or (isinstance(other, Unit) and other.offset != 0):
            raise TypeError("cannot divide units with non-zero offset")
        if isinstance(other, Unit):
            return Unit(other.names - self.names,
                        other.factor / self.factor,
                        [a - b for a, b in zip(other.powers, self.powers)],
                        self.offset,
                        other.lex_names - self.lex_names)
        else:
            return Unit({str(other): Ratio(1)} - self.names,
                        other / self.factor,
                        [-p for p in self.powers],
                        self.offset,
                        self.lex_names)

    def __pow__(self, other):
        if self.offset != 0:
            raise TypeError("cannot exponentiate units with non-zero offset")
        if isinstance(other, int):
            return Unit(other * self.names,
                        pow(self.factor, other),
                        [p * other for p in self.powers],
                        self.offset,
                        other * self.lex_names)
        if isinstance(other, float):
            inv_exp = 1./other
            rounded = int(floor(inv_exp+0.5))
            if abs(inv_exp-rounded) < 1.e-10:
                return self.__pow__(Ratio(1, rounded))
        if isinstance(other, Ratio):
            return Unit(other * self.names,
                        pow(self.factor, float(other)),
                        [p * other for p in self.powers],
                        self.offset,
                        other * self.lex_names)
        raise TypeError('Only integer, rational and inverse '\
                        'integer exponents allowed')

    def conversionFactorTo(self, other):
        """
        @param other: another unit
        @type other: L{Unit}
        @returns: the conversion factor from this unit to another unit
        @rtype: C{float}
        @raises TypeError: if the units are not compatible
        """
        if self.powers != other.powers or self.lex_names != other.lex_names:
            raise TypeError('Incompatible units')
        if self.offset != other.offset and self.factor != other.factor:
            raise TypeError(('Unit conversion (%s to %s) cannot be expressed ' +
                             'as a simple multiplicative factor') % \
                             (self.name(), other.name()))
        return self.factor/other.factor

    def conversionTupleTo(self, other): # added 1998/09/29 GPW
        """
        @param other: another unit
        @type other: L{Unit}
        @returns: the conversion factor and offset from this unit to
                  another unit
        @rtype: (C{float}, C{float})
        @raises TypeError: if the units are not compatible
        """
        if self.powers != other.powers or self.lex_names != other.lex_names:
            raise TypeError('Incompatible units')

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
        return (factor, offset)

    def isCompatible (self, other):     # added 1998/10/01 GPW
        """
        @param other: another unit
        @type other: L{Unit}
        @returns: C{True} if the units are compatible, i.e. if the powers of
                  the base units are the same
        @rtype: C{bool}
        """
        return self.powers == other.powers and self.lex_names == other.lex_names

    def isDimensionless(self):
        return (not any(self.powers)) and (sum(self.lex_names.values()) == 0)

    def isAngle(self):
        return self.powers[7] == 1 and \
               sum(self.powers) == 1 and \
               sum(self.lex_names.values()) == 0

    def setName(self, name):
        self.names = NumberDict()
        self.names[name] = 1
        self.lex_names = NumberDict()

    def name(self):
        num = ''
        denom = ''
        full_dict = dict(self.names, **self.lex_names)
        for unit in full_dict.keys():
            power = full_dict[unit]
            if power < 0:
                denom += '/' + unit
                if power != -1:
                    s = str(-power)
                    denom += '^' + s
            elif power > 0:
                num += '*' + unit
                if power != 1:
                    s = str(power)
                    num += '^' + s
        if len(num) == 0:
            num = '1'
        else:
            num = num[1:] # remove leading '*'
        name = num + denom
        if name == '1':
            return ''
        return name

    def labradName(self):
        name = self.name()
        if name == '1':
            name = ''
        return name


# Helper functions

def _findUnit(name):
    if not isinstance(name, basestring):
        unit = name
    elif name == '':
        return _ident()
    elif name in _unit_table:
        unit = _unit_table[name]
    else:
        result = grammar.unit.parseString(name)
        unit = _ident()
        for sign, list_ in [(1, result.posexp), (-1, result.negexp)]:
            if isinstance(list_, basestring):
                continue
            for elem in list_:
                try:
                    base = _unit_table[elem['name']]
                except KeyError:
                    base = _stringUnit(elem['name'])
                num = elem['num'] if 'num' in elem else 1
                denom = elem['denom'] if 'denom' in elem else 1
                unit = unit * base**(sign*Ratio(num, denom))
        _unit_table[name] = unit
    if not isinstance(unit, Unit):
        raise TypeError('%s is not a unit' % unit)
    return unit

def _ident():
    return Unit(NumberDict(), 1., [0,0,0,0,0,0,0,0,0], 0, NumberDict())

def _stringUnit(name):
    return Unit(NumberDict(), 1., [0,0,0,0,0,0,0,0,0], 0, name)

def _convertValue(value, src_unit, target_unit):
    (factor, offset) = src_unit.conversionTupleTo(target_unit)
    return (value + offset) * factor


# SI unit definitions

_base_names = ['m', 'kg', 's', 'A', 'K', 'mol', 'cd', 'rad', 'sr']

_base_units = [
    ('m',   Unit('m',   1.,    [1,0,0,0,0,0,0,0,0])),
    ('g',   Unit('g',   0.001, [0,1,0,0,0,0,0,0,0])),
    ('s',   Unit('s',   1.,    [0,0,1,0,0,0,0,0,0])),
    ('A',   Unit('A',   1.,    [0,0,0,1,0,0,0,0,0])),
    ('K',   Unit('K',   1.,    [0,0,0,0,1,0,0,0,0])),
    ('mol', Unit('mol', 1.,    [0,0,0,0,0,1,0,0,0])),
    ('cd',  Unit('cd',  1.,    [0,0,0,0,0,0,1,0,0])),
    ('rad', Unit('rad', 1.,    [0,0,0,0,0,0,0,1,0])),
    ('sr',  Unit('sr',  1.,    [0,0,0,0,0,0,0,0,1])),
    ]

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

_unit_table = {}

for unit in _base_units:
    _unit_table[unit[0]] = unit[1]

_help = []

def _addUnit(name, unit, comment=''):
    if name in _unit_table:
        raise KeyError, 'Unit ' + name + ' already defined'
    if comment:
        _help.append((name, comment, unit))
    if isinstance(unit, basestring):
	unit = eval(unit, _unit_table)
        for cruft in ['__builtins__', '__args__']:
            try: del _unit_table[cruft]
            except: pass
    unit.setName(name)
    _unit_table[name] = unit

def _addPrefixed(unit):
    _help.append('Prefixed units for %s:' % unit)
    _prefixed_names = []
    for prefix in _prefixes:
	name = prefix[0] + unit
	_addUnit(name, prefix[1]*_unit_table[unit])
        _prefixed_names.append(name)
    _help.append(', '.join(_prefixed_names))


# SI derived units; these automatically get prefixes
_help.append('SI derived units; these automatically get prefixes:\n' + \
     ', '.join([prefix + ' (%.0E)' % value for prefix, value in _prefixes]) + \
             '\n')


_unit_table['kg'] = Unit('kg', 1., [0,1,0,0,0,0,0,0,0])

_addUnit('Hz', '1/s', 'Hertz')
_addUnit('N', 'm*kg/s**2', 'Newton')
_addUnit('Pa', 'N/m**2', 'Pascal')
_addUnit('J', 'N*m', 'Joule')
_addUnit('W', 'J/s', 'Watt')
_addUnit('C', 's*A', 'Coulomb')
_addUnit('V', 'W/A', 'Volt')
_addUnit('F', 'C/V', 'Farad')
_addUnit('Ohm', 'V/A', 'Ohm')
_addUnit('S', 'A/V', 'Siemens')
_addUnit('Wb', 'V*s', 'Weber')
_addUnit('T', 'Wb/m**2', 'Tesla')
_addUnit('H', 'Wb/A', 'Henry')
_addUnit('lm', 'cd*sr', 'Lumen')
_addUnit('lx', 'lm/m**2', 'Lux')
_addUnit('Bq', '1/s', 'Becquerel')

del _unit_table['kg']

for unit in _unit_table.keys():
    _addPrefixed(unit)

# Time units
_help.append('Time units:')

_addUnit('min', '60*s', 'minute')
_addUnit('h', '60*min', 'hour')
_addUnit('d', '24*h', 'day')
_addUnit('y', '365.25*d', 'year')

# Length units
_help.append('Length units:')

_addUnit('inch', '2.54*cm', 'inch')
_addUnit('ft', '12*inch', 'foot')
_addUnit('mi', '5280.*ft', '(British) mile')

# Area units
_help.append('Area units:')

_addUnit('acre', 'mi**2/640', 'acre')

# Volume units
_help.append('Volume units:')

_addUnit('l', 'dm**3', 'liter')
_addUnit('dl', '0.1*l', 'deci liter')
_addUnit('cl', '0.01*l', 'centi liter')
_addUnit('ml', '0.001*l', 'milli liter')

# Force units
_help.append('Force units:')

_addUnit('dyn', '1.e-5*N', 'dyne (cgs unit)')

# Energy units
_help.append('Energy units:')

_addUnit('erg', '1.e-7*J', 'erg (cgs unit)')
_addUnit('eV', '1.6022e-19*C*V', 'electron volt')
_addUnit('cal', '4.184*J', 'thermochemical calorie')
_addUnit('kcal', '1000*cal', 'thermochemical kilocalorie')
_addUnit('Btu', '1055.05585262*J', 'British thermal unit')

_addPrefixed('eV')

# Power units
_help.append('Power units:')

_addUnit('hp', '745.7*W', 'horsepower')

# Pressure units
_help.append('Pressure units:')

_addUnit('bar', '1.e5*Pa', 'bar (cgs unit)')
_addUnit('atm', '101325.*Pa', 'standard atmosphere')
_addUnit('torr', 'atm/760', 'torr = mm of mercury')

# Angle units
_help.append('Angle units:')

_addUnit('deg', 'rad*3.14159265258979/180', 'degrees')

_help.append('Temperature units:')
# Temperature units -- can't use the 'eval' trick that _addUnit provides
# for degC and degF because you can't add units
kelvin = _findUnit('K')
_addUnit('degC', Unit(None, 1.0, kelvin.powers, 273.15), 'degrees Celcius')
_addUnit('degF', Unit(None, 5./9., kelvin.powers, 459.67), 'degree Fahrenheit')
del kelvin


# add units to the module namespace
for name, unit in _unit_table.items():
    globals()[name] = withUnits(1.0, unit)


# add constants to the module namespace
c       = 299792458.*m/s                   # speed of light
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
tsp     = 4.92892159375*ml # teaspoon
tbsp    = 3*tsp            # tablespoon
floz    = 2*tbsp           # fluid ounce
cup     = 8*floz           # cup
pint    = 16*floz          # pint
qt      = 2*pint           # quart
galUS   = 4*qt             # US gallon
galUK   = 4.54609*l        # British gallon
amu     = 1.6605402e-27*kg # atomic mass units
oz      = 28.349523125*g   # ounce
lb      = 16*oz            # pound
ton     = 2000*lb          # ton
Ken     = k*K              # Kelvin as energy unit
cali    = 4.1868*J         # international calorie
kcali   = 1000*cali        # international kilocalorie
psi     = 6894.75729317*Pa # pounds per square inch
degR    = (5./9.)*K        # degrees Rankine



def description():
    """Return a string describing all available units."""
    s = ''  # collector for description text
    for entry in _help:
        if isinstance(entry, basestring):
            # headline for new section
            s += '\n' + entry + '\n'
        elif isinstance(entry, tuple):
            name, comment, unit = entry
            s += '%-8s  %-26s %s\n' % (name, comment, unit)
        else:
            # impossible
            raise TypeError, 'wrong construction of _help list'
    return s

# add the description of the units to the module's doc string:
__doc__ += '\n' + description()

# Some demonstration code. Run with "python -i PhysicalQuantities.py"
# to have this available.

if __name__ == '__main__':

    l = withUnits(10., 'm')
    big_l = withUnits(10., 'km')
    print big_l + l
    t = withUnits(314159., 's')
    print t.inUnitsOf('d','h','min','s')

    p = withUnits # just a shorthand...

    e = p('2.7 Hartree*Nav')
    e.convertToUnit('kcal/mol')
    print e
    print e.inBaseUnits()

    freeze = p('0 degC')
    print freeze.inUnitsOf ('degF')
