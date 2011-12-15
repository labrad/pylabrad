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

from labrad import units

class LabradUnitsTests(unittest.TestCase):
    def testParsing(self):
        # prefixes
        # multiplication
        # division
        # powers
        pass
        
    def testArithmetic(self):
        m = units.Unit('m')
        kg = units.Unit('kg')
        
        self.assertEqual(units.Value(5.0, None)*m, 5.0*m)
        
        # addition
        self.assertEqual(1.0*kg + 0.0, 1.0*kg)
        
        self.assertNotEqual(1.0*kg, None)
        

