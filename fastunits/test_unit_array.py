#!/usr/bin/python
import unittest
import unitarray

class UnitsArrayTests(unittest.TestCase):
    def testConstruction(self):
        x = unitarray.UnitArray('km')
        y = unitarray.UnitArray('m')
        self.assertEquals(repr(x/y), 'UnitArray("km/m")')

def perf_unit_array(N=10000):
    x = unitarray.UnitArray('km')
    y = unitarray.UnitArray('m')
    for j in range(N):
        z = x*y
    
if __name__ == "__main__":
    unittest.main()

