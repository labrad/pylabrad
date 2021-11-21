# Copyright (C) 2007  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import math
import pickle

import numpy as np
import pytest

from labrad import units
from labrad.units import Value, ValueArray


class LabradUnitsTests:
    def test_parsing(self):
        # prefixes
        # multiplication
        # division
        # powers
        pass

    def test_arithmetic(self):
        m = units.Unit('m')
        kg = units.Unit('kg')
        km = units.Unit('km')

        #self.assertEqual(units.Value(5.0, None)*m, 5.0*m)

        # addition
        assert 1.0*kg + 0.0 == 1.0*kg
        with pytest.raises(TypeError):
            _ = 1.0*kg + 1.0*m
        with pytest.raises(TypeError):
            _ = 1.0*kg + 2.0
        assert math.isclose(1.0*km/m + 5.0, 1005)
        assert 1.0*kg != None

    @pytest.mark.xfail()  # TODO: fix isfinite on ValueArray
    def test_value_array(self):
        # Slicing
        assert (ValueArray([1, 2, 3], 'm')[0:2] == ValueArray([1, 2], 'm')).all()
        # Cast to unit
        assert (ValueArray([1.2, 4, 5], 'm')['m'] == np.array([1.2, 4, 5])).all()
        # Addition and subtraction of compatible units
        assert (ValueArray([3, 4], 'm') + ValueArray([100, 200], 'cm') ==
                ValueArray([4, 6], 'm')).all()
        assert (ValueArray([2, 3, 4], 'm') - ValueArray([100, 200, 300], 'cm') ==
                ValueArray([1, 1, 1], 'm')).all()
        # Division with units remaining
        assert (ValueArray([3, 4, 5], 'm') / ValueArray([1, 2, 5], 's') ==
                ValueArray([3, 2, 1], 'm/s')).all()
        # Division with no units remaining
        assert (ValueArray([3, 4, 5], 'm') / ValueArray([1, 2, 5], 'm') ==
                ValueArray([3, 2, 1], '')).all()
        # Powers
        assert (ValueArray([2, 3], 'm')**2 == ValueArray([4, 9], 'm^2')).all()

        assert (ValueArray([2, 3], 'GHz') * Value(3, 'ns')).dtype == np.float64

        # isfinite
        assert np.isfinite(ValueArray([1, 2], 'GHz')).all()
        assert (np.isfinite(ValueArray([1, float('nan')], 'GHz')) == np.array([True, False])).all()

    def test_value_array_construction(self):
        v1 = ValueArray([Value(1, 'MHz'), Value(1, 'GHz')])
        v2 = ValueArray([1, 1000], 'MHz')
        assert (v1 == v2).all()

    def test_negative_powers(self):
        assert str(units.Unit('1/s')) == 's^-1'
        assert str(units.Unit('1/s^1/2')) == 's^-1/2'

    def test_type_conversions(self):
        m = units.Unit('m')
        V = units.Unit('V')
        GHz = units.Unit('GHz')
        x1 = 1.0*m
        x2 = 5j*V
        a = np.arange(10)*1.0
        va = units.ValueArray(np.arange(10)*1.0, 'GHz')

        # Unit times number
        assert isinstance(1.0*m, units.Value)
        assert isinstance(1*m, units.Value)
        assert isinstance(m*1.0, units.Value)
        assert isinstance(m*1, units.Value)

        # Value times value or number
        assert isinstance(x1*x1, units.Value)
        assert isinstance(x1*5, units.Value)
        assert isinstance(0*x1, units.Value)

        # Unit times complex
        assert isinstance((1+1j)*V, units.Complex)
        assert isinstance(V*(1+1j), units.Complex)

        # Value times Complex/complex
        assert isinstance(x1*1j, units.Complex)
        assert isinstance(1j*x1, units.Complex)
        assert isinstance(x2*x1, units.Complex)
        assert isinstance(x1*x2, units.Complex)

        # Unit/Value/ValueArray times array
        assert isinstance(x1*a, units.ValueArray)
        assert isinstance(x2*a, units.ValueArray)
        assert isinstance(GHz*a, units.ValueArray)
        assert isinstance(va*a, units.ValueArray)

        # Unit/Value/ValueArray times ValueArray
        assert isinstance(x1*va, units.ValueArray)
        assert isinstance(x2*va, units.ValueArray)
        assert isinstance(GHz*va, units.ValueArray)
        assert isinstance(va*va, units.ValueArray)

        # array times ?
        assert isinstance(a*x1, units.ValueArray)
        assert isinstance(a*x2, units.ValueArray)
        assert isinstance(a*GHz, units.ValueArray)
        assert isinstance(a*va, units.ValueArray)

        # ValueArray times ?
        assert isinstance(va*x1, units.ValueArray)
        assert isinstance(va*x2, units.ValueArray)
        assert isinstance(va*GHz, units.ValueArray)
        assert isinstance(va*a, units.ValueArray)

    def test_comparison(self):
        s = units.Unit('s')
        ms = units.Unit('ms')
        kg = units.Unit('kg')
        assert 1*s > 10*ms
        assert 1*s >= 10*ms
        assert 1*s < 10000*ms
        assert 1*s <= 10000*ms
        assert 10*ms < 1*s
        assert 10*ms <= 1*s
        assert 10000*ms > 1*s
        assert 10000*ms >= 1*s
        with pytest.raises(TypeError):
            nogood = 1*s > 1*kg

        assert 1*s != 1*kg
        assert 0*s == 0
        assert 4*s > 0
        with pytest.raises(TypeError):
            _ = 4*s > 1

    def test_complex(self):
        V = units.Unit('V')

        assert 1j*V != 1.0*V
        assert 1j*V == 1.0j*V
        assert 1.0*V == (1+0j)*V
        with pytest.raises(TypeError):
            _ = 1.0j*V < 2j*V

    def test_dimensionless(self):
        ns = units.Unit('ns')
        GHz = units.Unit('GHz')

        assert isinstance((5*ns)*(5*GHz), float)
        assert hasattr((5*ns)*(5*GHz), 'inUnitsOf')
        assert ((5*ns)*(5*GHz)).isDimensionless()
        assert (5*ns)*(5*GHz) < 50
        assert isinstance(units.WithUnit(5.0, ''), units.DimensionlessFloat)

        assert (5*ns*5j*GHz) == 25j
        assert (5*ns*5j*GHz).isDimensionless()

    def test_angle(self):
        rad = units.Unit('rad')
        assert rad.is_angle
        assert rad.isAngle()
        x = units.Unit('rad*m/s')
        assert not x.is_angle

    def test_inf_nan(self):
        ms = units.Unit('ms')
        GHz = units.Unit('GHz')
        MHz = units.Unit('MHz')
        
        assert float('inf')*GHz == float('inf')*MHz
        assert float('inf')*GHz != float('inf')*ms
        assert float('inf')*GHz != -float('inf')*GHz
        assert float('nan')*GHz != float('nan')*GHz
        assert float('nan')*GHz != float('nan')*ms

    def test_pickling(self):
        ns = units.Unit('ns')
        GHz = units.Unit('GHz')
        blank = units.Unit('')

        def round_trip(obj):
            return pickle.loads(pickle.dumps(obj))
        assert round_trip(5*GHz) == 5*GHz  # Value
        assert round_trip(GHz) == GHz  # Unit
        assert (round_trip(np.arange(5)*ns) == np.arange(5)*ns).all()  # array
        assert round_trip(5*GHz*ns) == 5  # Dimensionless
        assert isinstance(round_trip(3*blank), type(3*blank)) # Don't loose dimensionless type

    def test_unit_creation(self):
        assert isinstance(units.Unit('test0', 1.0, units.hplanck/(2*units.e)), units.Unit)
        assert (units.Unit('phi0')**2).isCompatible(units.Unit('phi0^2'))

    def test_in_units_of(self):
        s = units.Unit('s')
        ms = units.Unit('ms')
        assert (1*s).inUnitsOf(ms) == 1000*ms
        assert (1*s).inUnitsOf('ms') == 1000*ms

    def test_base_unit_powers(self):
        x = Value(1, 'ns^2')

        assert x.unit.base_unit == units.Unit('s^2')
        assert x.inBaseUnits() == Value(1e-18, 's^2')

    def test_unit_powers(self):
        assert units.Unit('ns')**2 == units.Unit('ns^2')

    def test_array_priority(self):
        """numpy issue 6133

        DimensionlessX needs to support all arithmetic operations when the
        other side is an array.  Numpy's __array_priority__ machinery doesn't
        handle NotImplemented results correctly, so the higher priority element
        *must* be able to handle all operations.

        In numpy 1.9 this becomes more critical because numpy scalars like np.float64
        get converted to arrays before being passed to binary arithmetic operations.
        """
        x = np.float64(1)
        y = units.DimensionlessFloat(2)
        assert x < y
        z = np.arange(5)
        assert ((x<z) == [False, False, True, True, True]).all()

    def testNone(self):
        with pytest.raises(Exception):
            units.Unit(None)
        with pytest.raises(TypeError):
            None * units.Unit('MHz')

    def test_non_SI(self):
        units.addNonSI('count', True)
        x = 5 * units.Unit('kcount')
        assert x['count'] == 5000.0
        assert x.inBaseUnits() == 5000.0*units.Unit('count')
        assert (x**2).unit == units.Unit('kcount^2')

    def test_string_unit(self):
        ts = units.Unit('tshirt/s')
        assert (1*ts)['tshirt/h'] == 3600.0
        assert str(ts) == 'tshirt/s'
