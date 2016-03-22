#!/usr/bin/python

import unittest
import fastunits as U
from fastunits import Value, Unit, Complex, ValueArray, UnitMismatchError
import numpy as np

class FastUnitsTests(unittest.TestCase):
    def testConstruction(self):
        x = 2*Unit('')
        y = Value(5, 'ns')
        self.assertIsInstance(x, Value)
        self.assertIsInstance(y, Value)
        self.assertTrue(x.isDimensionless())
        self.assertIsInstance(3j*x, Complex)
        self.assertIsInstance(np.arange(5)*U.ns, ValueArray)

    def testDimensionless(self):
        """Test that dimensionless values act like floats"""
        x = Value(1.5, '')
        y = Value(1.5, 'us/ns')
        self.assertEqual(x, 1.5)
        self.assertEqual(np.ceil(x), 2.)
        self.assertEqual(np.floor(x), 1.)
        self.assertEqual(y, 1500.)
    
    def testValueArraySlicing(self):
        x = np.arange(5)*U.ns
        self.assertTrue(np.allclose(x[::2]['ns'], np.array([0., 2., 4.])))
        
    def testAddition(self):
        n = Value(2, '')
        x = Value(1.0, U.kilometer);
        y = Value(3, 'meter');
        a = Value(20, 's');
        self.assertEqual(x + y, Value(1003, 'meter'))
        self.assertNotEqual(x, y)
        self.assertNotEqual(x, a)
        with self.assertRaises(UnitMismatchError):
            _ = y + a 
        with self.assertRaises(UnitMismatchError):
            _ = x + 3.0
        _ = x + y
        self.assertEqual(x-y, Value(997, 'm'))
        self.assertIsInstance(x*1j + y, Complex)
        self.assertEqual(n+1, 3)

    def testMultiplication(self):
        n = Value(2, '')
        x = Value(1.0+2j, U.meter)
        y = Value(3, U.mm)
        z = np.arange(5)*U.ns
        a = Value(20, U.second)
        self.assertEqual(a*x, x*a)
        self.assertTrue((x/y).isDimensionless())
        self.assertTrue((z/U.ns).isDimensionless())
        self.assertIsInstance(z/U.ns, ValueArray)
        self.assertTrue(np.allclose(z*Value(5, 'GHz'), z['ns']*5))
        
    def testPower(self):
        x = 2*U.mm
        y = 4*U.mm
        z = (x*y)**.5
        self.assertLess(abs(z**2- Value(8, 'mm^2')),  Value(1e-6, U.mm**2))

    def testStringification(self):
        x = Value(4, U.mm)
        self.assertEqual(repr(x), 'Value(4.0, "mm")')
        self.assertEqual(str(x), '4.0 mm');
        
    def testDivmod(self):
        x = 4.001*U.us
        self.assertEquals(x//(4*U.ns), 1000)
        self.assertEquals(x % (4*U.ns), x - 1000*4*U.ns)
        q,r = divmod(x, 2*U.ns)
        self.assertEquals(q, 2000)
        self.assertEquals(r, x - q*2*U.ns)

    def testConversion(self):
        x = Value(3, 'm')
        self.assertEquals(x['mm'], 3000.0)
        with self.assertRaises(UnitMismatchError):
            x['s']
        y = Value(1000, 'Mg')
        self.assertEquals(y.inBaseUnits().value, 1000000.0)
        self.assertEquals(x.inUnitsOf('mm'), 3000*U.mm)

    def testFloatRatio(self):
        # Years always use floating point ratio
        x = Value(1, 'yr')
        self.assertIsInstance(x.numer, float)
        self.assertEquals(x.denom, 0)

        # a mile is exactly 16093440 * 10^-4 meters, this makes mile^3 overflow and forces floating point representation.
        x = Value(1, 'mile')
        y = x**3

        self.assertIsInstance(x.numer, (int, long))
        self.assertNotEquals(x.denom, 0)
        self.assertIsInstance(y.numer, float)
        self.assertEquals(y.denom, 0)

    def testHash(self):
        x = Value(3, 'ks')
        y = Value(3000, 's')
        self.assertEquals(hash(x), hash(y))
        z = Value(3.1, '')
        self.assertEquals(hash(z), hash(3.1))
        hash(Value(4j, 'V'))

if __name__ == "__main__":
    unittest.main()
