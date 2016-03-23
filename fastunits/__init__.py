#!/usr/bin/env python
"""
fastunits is a mostly-C implementation of the labrad "units.py" with ~100x performance improvement over the python
implementation.


"""
from __future__ import division

import math
import numpy as np

import fastunits.unitarray as unitarray
from fastunits.unitarray import WithUnit, Value, Complex, ValueArray, UnitMismatchError
import fastunits.unit_grammar as unit_grammar

_unit_cache = {}
class Unit(object):
    """Unit database.

    Values defined in unit_array do not actually store a unit object, the unit names and powers
    are stored within the value object itself.  However, when constructing new values or converting
    betwee units, we need a database of known units.
    """
    __array_priority__ = 15
    __slots__ = ['_value']

    def __new__(cls, name):
        if isinstance(name, Unit):
            return name
        if name in _unit_cache:
            return _unit_cache[name]
        else:
            return cls.parse_unit_str(name)

    # The following methods are internal constructors used to generate new unit instances
    # to separate that out from the main __new__ method which users will use to construct
    # objects from strings.
    @classmethod
    def _new_from_value(cls, val):
        if not isinstance(val, unitarray.WithUnit):
            raise RuntimeError("Need Value type to create unit")
        if val._value != 1.0:
            raise RuntimeError("Cannot create unit from a value not of unit magnitude")
        obj = object.__new__(cls)
        obj._value = val
        return obj

    @classmethod
    def _unit_from_parse_item(cls, item, neg=0):
        base_name = item.name
        numer = item.num or 1
        denom = item.denom or 1
        sign = -1 if item.neg else 1
        if neg:
            sign = -sign
        if base_name not in _unit_cache:
            base_unit = unitarray.UnitArray(base_name)
            _unit_cache[base_name] = Unit._new_from_value(WithUnit._new_raw(1, numer=1, denom=1, exp10=0, base_units=base_unit, display_units=base_unit))
        element = _unit_cache[base_name]**(1.0*sign*numer/denom)
        return element

    @classmethod
    def _new_derived_unit(cls, name, numer, denom, exp10, base_unit):
        if isinstance(base_unit, str):
            base_unit = Unit(base_unit)
        numer = numer * base_unit._value.numer
        denom = denom * base_unit._value.denom
        exp10 = exp10 + base_unit._value.exp10
        val = WithUnit._new_raw(1, numer=numer, denom=denom, exp10=exp10, base_units=base_unit._value.base_units, display_units=unitarray.UnitArray(name))
        result = cls._new_from_value(val)
        _unit_cache[name] = result
        return result

    @classmethod
    def _new_base_unit(cls, name):
        if name in _unit_cache:
            raise RuntimeError("Trying to create unit that already exists")
        ua = unitarray.UnitArray(name)
        val = WithUnit._new_raw(1, numer=1, denom=1, exp10=0, base_units=ua, display_units=ua)
        result = cls._new_from_value(val)
        _unit_cache[name] = result
        return result

    @classmethod
    def parse_unit_str(cls, name):
        parsed = unit_grammar.unit.parseString(name)
        result = Unit('')
          
        for item in parsed.posexp:
            element = cls._unit_from_parse_item(item, 0)
            result = result * element
        for item in parsed.negexp:
            result = result * cls._unit_from_parse_item(item, -1)
        return result

    # Unit arithmetic is used in two ways: to build compound units
    # or to build new Value instances by multiplying a scalar by
    # a unit object.  Since a "Unit" just has an internal value,
    # representing its units, the later just gets delegated to 
    # Value arithmetic.
    def __mul__(self, other):
        if isinstance(other, Unit):
            return Unit._new_from_value(other._value * self._value)
        result = other * self._value
        return result

    __rmul__ = __mul__
    
    def __div__(self, other):
        if isinstance(other, Unit):
            return Unit._new_from_value(self._value/other._value)
        return self._value/other

    def __rdiv__(self, other):
        if isinstance(other, Unit):
            return Unit._new_from_value(other._value/self._value)
        result = other/self._value
        return result

    def __pow__(self, other):
        return Unit._new_from_value(self._value**other)

    def __copy__(self):
        """Units are immutable, so __copy__ just returns self.
        """
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        return (Unit, (str(self),) )
    
    @property
    def name(self):
        return str(self)

    def __repr__(self):
        return "<Unit '%s'>" % (str(self._value.display_units),)

    def __str__(self):
        return str(self._value.display_units)
    
    def __eq__(self, other):
        if not isinstance(other, Unit):
            return NotImplemented
        return self._value == other._value

    def __ne__(self, other):
        return not (self == other)

    def conversionFactorTo(self, other):
        if not isinstance(other, Unit):
            raise TypeError("conversionFactorTo called on non-unit")
        if self._value.base_units != other._value.base_units:
            raise TypeError("incompabile units '%s', '%s'" % (self.name, other.name))
        ratio = self._value / other._value
        return ratio.inBaseUnits()._value

    def converstionTupleTo(self, other):
        """Deprecated.
        
        This was needed for support of degree scales with zero offsets like degF and degC.  This library
        doesn't support them, so offset is always 0.
        """
        factor = self.conversionFactorTo(other)
        return factor,0

    def isDimensionless(self):
        return self._value.isDimensionless()

    def isCompatible(self, other):
        self._value.base_units == other._value.base_units
        
    def isAngle(self):
        return self._value.base_units == _unit_cache['rad']._value.base_units

    is_angle = property(isAngle)


    
# The next two methods are called from the C implementation
# of Value() to implement the parts of the API that interact
# with Unit objects (in particular, the cache of known unit
# instances)-- unit conversion and new object creation.  
# It is not allowed to directly modify C PyTypeObjects from python
# so we need a helper method to set these, which is done in
# Value._set_py_func


def _unit_val_from_str(unitstr):
    """Lookup a unit by name.

    This is a helper called when WithUnit objects need to lookup a unit
    string.  We return the underlying _value, because that is what the C
    API knows how to handle."""
    unit = Unit(unitstr)
    return unit._value

@property
def _value_unit(self):
    """This is called by Value to implement the .unit property"""
    v = WithUnit._new_raw(1, numer=self.numer, denom=self.denom, exp10=self.exp10, base_units=self.base_units, display_units=self.display_units)
    return Unit._new_from_value(v)

def allclose(self, other, *args, **kw):
    return np.allclose(self._value, other[self.unit], *args, **kw)

WithUnit._set_py_func(_value_unit, Unit, _unit_cache, allclose)


class OffsetUnit(object):
    """
    Used for degF and degC unit objects.
    """
    __array_priority__ = 15
    _cache = {}
    def __new__(cls, name):
        return cls._cache[name]
    
    @classmethod
    def _new_raw(cls, name, scale_factor, offset):
        obj = object.__new__(cls)
        obj.name = name
        obj.offset = offset
        obj.scale_factor = scale_factor
        cls._cache[name] = obj
        return obj
    
    def __mul__(self, other):
        try:
            return (other * self.scale_factor * self.offset.unit) + self.offset
        except Exception:
            raise TypeError("Offset units can only be multiplied by dimensionless values.")

    __rmul__ = __mul__

_unit_cache[''] = Unit._new_from_value(WithUnit._new_raw(1,numer=1,denom=1,exp10=0, base_units=unitarray.DimensionlessUnit, display_units=unitarray.DimensionlessUnit))

SI_PREFIX_SHORT = ['Y', 'Z', 'E', 'P', 'T', 'G', 'M', 'k', 'h', 'da', 'd', 'c', 'm', 'u', 'n', 'p', 'f', 'a', 'z', 'y']
SI_PREFIX_LONG = ['yotta', 'zetta', 'exa', 'peta', 'tera', 'giga', 'mega', 'kilo', 'hecto', 'deka', 'deci', 'centi', 'milli', 'micro', 'nano', 'pico', 'femto', 'atto', 'zepto', 'yocto']
SI_PREFIX_POWER = [ 24,  21,  18,  15,  12,   9,  6,   3,   2,   1,   -1,  -2,  -3,  -6,  -9,  -12, -15, -18, -21, -24]
SI_BASE_UNITS = ['m', 'kg', 's', 'A', 'K', 'mol', 'cd', 'rad', 'sr']
SI_BASE_UNIT_FULL = ['meter', 'kilogram', 'second', 'ampere', 'kelvin', 'mole', 'candela', 'radian', 'steradian']

for name, long_name in zip(SI_BASE_UNITS, SI_BASE_UNIT_FULL):
    Unit._new_base_unit(name)
    Unit._new_derived_unit(long_name, 1, 1, 0, name)
    
    if (name == 'kg'):
        Unit._new_derived_unit('g', 1, 1, -3, name)
        Unit._new_derived_unit('gram', 1, 1, -3, name)
        name = 'g'
        long_name = 'gram'

    for short_prefix, long_prefix, power in zip(SI_PREFIX_SHORT, SI_PREFIX_LONG, SI_PREFIX_POWER):
        if (name == 'g' and short_prefix == 'k'):
            continue
        Unit._new_derived_unit(short_prefix+name, 1, 1, power, name)
        Unit._new_derived_unit(long_prefix+long_name, 1, 1, power, name)

# SI derived units are units derived from multiple SI base units.  They can be
# prefixed by standard SI prefixes.  They always have a multiplier of 1.

SI_DERIVED_UNITS = [
    ('Hz', 'hertz', '1/s'),
    ('N', 'newton', 'kg*m/s^2'),
    ('Pa', 'pascal', 'N/m^2'),
    ('J', 'joule', 'N*m'),
    ('W', 'watt', 'J/s'),
    ('C', 'coulomb', 'A*s'),
    ('V', 'volt', 'W/A'),
    ('F', 'farad', 'J/C'),
    ('Ohm', 'ohm', 'V/A'),
    ('S', 'siemens', 'A/V'),
    ('W', 'weber', 'V*s'),
    ('T', 'tesla', 'Wb/m^2'),
    ('H', 'henry', 'Wb/A'),
    ('lm', 'lumen', 'cd*sr'),
    ('lx', 'lux', 'lm/m^2'),
    ('Bq', 'becqurel', 'Hz'),
    ]

for (short_name, long_name, base) in SI_DERIVED_UNITS:
    Unit._new_derived_unit(short_name, 1, 1, 0, base)
    Unit._new_derived_unit(long_name, 1, 1, 0, base)
    for short_prefix, long_prefix, power in zip(SI_PREFIX_SHORT, SI_PREFIX_LONG, SI_PREFIX_POWER):
        Unit._new_derived_unit(short_prefix+short_name, 1, 1, power, base)
        Unit._new_derived_unit(long_prefix+long_name, 1, 1, power, base)

# These units are not SI derived.  They fall into two classes:
# non-standard variations on SI units, such as those derived from the
# cgs unit system, or units like the barn (10^-28 meter), or non-metric
# units such as imperial units, and minute/hour/day/year.  This is also
# the place for "physically derived" units like light-year and eV.
#
# Format:
# (shortname, longname, baseunit, numer, denom, exp10)
#
# If denom > 0, numer should be an integer:
# shortname == longname == baseunit * numer/denom * 10^exp10
#
# If denom = 0, numer should be a float:
# shortname == longname == baseunit * numer * 10^exp10
#
# Either shortname or longname may be None, in which case it will be
# ignored



NON_SI_UNITS = [
    ('in', 'inch', 'cm', 254, 1, -2),
    ('ft', 'foot', 'inch', 12, 1, 0),
    ('mi', 'mile', 'foot', 5280, 1, 0),
    (None, 'acre', 'mi^2', 1, 640, 0),
    ('d', 'day', 's', 864, 1, 2),
    ('h', 'hour', 's', 36, 1, 2),
    ('min', 'minute', 's', 6, 1, 1),
    ('yr', 'year', 'day', 365.242, 0, 0),
    ('deg', 'degree', 'rad', math.pi/180.0, 0, 0),
    ('cc', None, 'cm^3', 1, 1, 0),
    (None, 'dyne', 'N', 1, 1, -5),
    (None, 'erg', 'J', 1, 1, -7),
    ('cal', 'calorie', 'J', 4.184, 0, 0),
    ('b', 'barn', 'm^2', 1, 1, -28),
    ('kcal', 'kilocalorie', 'cal', 1, 1, 3),
    (None, 'gauss', 'T', 1, 1, -5),
    ('BTU', None, 'J', 1055.05585262, 0, 0),
    ('hp', 'horsepower', 'W', 745.7, 0, 0),
    ('atm', 'atmosphere', 'Pa', 101325.0, 0, 0),
    ('psi', None, 'Pa', 6894.76, 0, 0),
    ('degR', 'rankine', 'K', 5, 9, 0)
    ]

for (short_name, long_name, base, numer, denom, exp10) in NON_SI_UNITS:
    if short_name: Unit._new_derived_unit(short_name, numer, denom, exp10, base)
    if long_name: Unit._new_derived_unit(long_name, numer, denom, exp10, base)


# These are units that are non-SI but used with SI Prefixes.  It is
# recommended to not add units here that are not commonly used with
# multiple prefixes, as it pollutes the namespace.  If a particular
# unit is only commonly used with one or two prefixes consider adding
# it explicitly in the NON_SI_UNITS table.  For example see the
# 'kcal/kilocalorie' example above.
#
# The format is the same as NON_SI_UNITS.  Like regular SI units, the
# short name will get 'k, M, G' style prefixes, while the long name
# (if present) will get kilo-, mega-, and giga-.

PREFIXABLE_NON_SI_UNITS = [
    ('eV', None, 'J', 1.060218e-19, 0, 0),
    ('bar', None, 'Pa', 1, 1, 5),
    ('torr', None, 'Pa', 133.322, 0, 0),
    ('l', 'liter', 'm^3', 1, 1, -3),
    ]

for (short_name, long_name, base, numer, denom, exp10) in PREFIXABLE_NON_SI_UNITS:
    if short_name:
        Unit._new_derived_unit(short_name, numer, denom, exp10, base)
    if long_name and long_name != short_name:
        Unit._new_derived_unit(long_name, numer, denom, exp10, base)
    for short_prefix, long_prefix, power in zip(SI_PREFIX_SHORT, SI_PREFIX_LONG, SI_PREFIX_POWER):
        if short_name: Unit._new_derived_unit(short_prefix+short_name, numer, denom, exp10+power, base)
        if long_name: Unit._new_derived_unit(long_prefix+long_name, numer, denom, exp10+power, base)

# These are non-SI base units -- they are not dimensionally compatible
# with any SI units.  dB and dBm are examples here (we don't do any
# special handling for logarithmic units), but this could be used for
# domain specific units that don't need any special conversions.

def addNonSI(name=None, prefixable=False, long_name=None):
    base = None
    if name:
        base = Unit._new_base_unit(name)
    if long_name and not name:
        base = Unit._new_derived(long_name)
    if long_name and name:
        Unit._new_derived_unit(long_name, 1, 1, 0, base)
    if not base:
        raise ValueError("Must provide either name or long_name")
    
    if prefixable:
       for short_prefix, long_prefix, power in zip(SI_PREFIX_SHORT, SI_PREFIX_LONG, SI_PREFIX_POWER):
            if name:
                Unit._new_derived_unit(short_prefix+name, 1, 1, power, base)
            if long_name:
                Unit._new_derived_unit(long_prefix+long_name, 1, 1, power, base)

OTHER_BASE_UNITS = [
    'dB', 'dBm']
for name in OTHER_BASE_UNITS:
    addNonSI(name)


# Make all the unit objects module variables.
for k,v in _unit_cache.items():
    globals()[k] = v

degC = OffsetUnit._new_raw('degC', 1.0, 273.15*K)
degF = OffsetUnit._new_raw('degF', 1.0, 459.67*degR)

constants = {}
def _set_constants():
    pi = math.pi
    _c = constants
    _c['c'] = Value(299792458., 'm/s')
    _c['mu0'] = Value(4.e-7*pi, 'N/A^2')                  # permeability of vacuum
    _c['eps0'] = 1/_c['mu0']/_c['c']**2                       # permittivity of vacuum
    _c['G'] = Value(6.67259e-11, 'm^3/kg/s^2')         # gravitational constant
    _c['hplanck'] = Value(6.62606957e-34, 'J*s')               # Planck constant
    _c['hbar'] = _c['hplanck']/(2*pi)                   # Planck constant / 2pi
    _c['e'] = Value(1.60217733e-19, 'C')                 # elementary charge
    _c['me'] = Value(9.1093897e-31, 'kg')                 # electron mass
    _c['mp'] = Value(1.6726231e-27, 'kg')                 # proton mass
    _c['Nav'] = Value(6.0221367e23, '1/mol')                 # Avogadro number
    _c['k'] = Value(1.380658e-23, 'J/K')                 # Boltzmann constant
    _c['Bohr'] = 4*pi*_c['eps0']*_c['hbar']**2/_c['me']/_c['e']**2        # Bohr radius
    _c['Hartree'] = _c['me']*_c['e']**4/16/pi**2/_c['eps0']**2/_c['hbar']**2 # Wavenumbers/inverse cm

_set_constants()
'''
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
'''
    
