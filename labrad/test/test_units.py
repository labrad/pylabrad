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

import unittest
import numpy as np

import sys
import os
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath('../..'))
from labrad import units
ValueArray = units.ValueArray
Value = units.Value

class LabradUnitsTests(unittest.TestCase):
    def testParsing(self):
        # prefixes
        # multiplication
        # division
        # powers
        pass
    
    def testNullUnits(self):
            expected = Value(2.0, '')
            aliases = [Value(2.0, None)]
            for alias in aliases:
                self.assertEqual(alias, expected)
    
    def testArithmetic(self):
        m = units.Unit('m')
        kg = units.Unit('kg')
        km = units.Unit('km')
        
        self.assertEqual(units.Value(5.0, None)*m, 5.0*m)
        
        # addition
        self.assertEqual(1.0*kg + 0.0, 1.0*kg)
        with self.assertRaises(TypeError): _ = 1.0*kg + 1.0*m
        with self.assertRaises(TypeError): _ = 1.0*kg + 2.0
        self.assertAlmostEqual(1.0*km/m + 5.0, 1005)
        self.assertNotEqual(1.0*kg, None)
    
    def test_valueArray(self):
        # Slicing
        self.assertTrue((ValueArray([1,2,3], 'm')[0:2] == ValueArray([1,2], 'm')).all())
        # Cast to unit
        self.assertTrue((ValueArray([1.2, 4, 5], 'm')['m'] == np.array([1.2, 4, 5])).all())
        # Addition and subtraction of compatible units
        self.assertTrue((ValueArray([3,4], 'm') + ValueArray([100, 200], 'cm') == 
                         ValueArray([4, 6], 'm')).all())
        self.assertTrue((ValueArray([2, 3, 4], 'm') - ValueArray([100, 200, 300], 'cm') ==
                         ValueArray([1, 1, 1], 'm')).all())
        # Division with units remaining
        self.assertTrue((ValueArray([3, 4, 5], 'm') / ValueArray([1, 2, 5], 's') ==
                         ValueArray([3, 2, 1], 'm/s')).all())
        # Division with no units remaining
        self.assertTrue((ValueArray([3, 4, 5], 'm') / ValueArray([1, 2, 5], 'm') ==
                         ValueArray([3, 2, 1], '')).all())
        # Powers
        self.assertTrue((ValueArray([2, 3], 'm')**2 == ValueArray([4, 9], 'm^2')).all())
    
    def testNegativePowers(self):
        self.assertEqual(str(units.Unit('1/s')), 's^-1')
        self.assertEqual(str(units.Unit('1/s^1/2')), 's^-1/2')
    
    def testComparison(self):
        s = units.Unit('s')
        ms = units.Unit('ms')
        kg = units.Unit('kg')
        self.assertTrue(1*s > 10*ms, '1*s > 10*ms')
        self.assertTrue(1*s >= 10*ms, '1*s >= 10*ms')
        self.assertTrue(1*s < 10000*ms, '1*s > 10000*ms')
        self.assertTrue(1*s <= 10000*ms, '1*s >= 10000*ms')
        self.assertTrue(10*ms < 1*s, '10*ms < 1*s')
        self.assertTrue(10*ms <= 1*s, '10*ms <= 1*s')
        self.assertTrue(10000*ms > 1*s, '10000*ms < 1*s')
        self.assertTrue(10000*ms >= 1*s, '10000*ms <= 1*s')
        with self.assertRaises(TypeError):
            nogood = 1*s > 1*kg

        self.assertFalse(1*s == 1*kg)
        self.assertTrue(0*s == 0)
        self.assertTrue(4*s > 0)
        with self.assertRaises(TypeError): _ = 4*s > 1
    
    def testComplex(self):
        V = units.Unit('V')

        self.assertTrue(1j*V != 1.0*V)
        self.assertTrue(1j*V == 1.0j*V)
        self.assertTrue(1.0*V == (1+0j)*V)
        with self.assertRaises(TypeError): _ = 1.0j*V < 2j*V

if __name__ == "__main__":
    unittest.main()
