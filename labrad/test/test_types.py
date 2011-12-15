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

from datetime import datetime
import unittest

from labrad import types as T
from labrad import units as U

class LabradTypesTests(unittest.TestCase):
    def testTags(self):
        """Test the parsing of type tags into LRType objects."""
        tests = {
            '': T.LRNone(),
            'b': T.LRBool(),
            'i': T.LRInt(),
            'w': T.LRWord(),
            's': T.LRStr(),
            't': T.LRTime(),

            # clusters
            'ii': T.LRCluster(T.LRInt(), T.LRInt()),
            'b(t)': T.LRCluster(T.LRBool(), T.LRCluster(T.LRTime())),
            '(ss)': T.LRCluster(T.LRStr(), T.LRStr()),
            '(s)': T.LRCluster(T.LRStr()),
            '((siw))': T.LRCluster(T.LRCluster(T.LRStr(), T.LRInt(),
                                               T.LRWord())),
            
            # lists
            '*b': T.LRList(T.LRBool()),
            '*_': T.LRList(),
            '*2b': T.LRList(T.LRBool(), depth=2),
            '*2_': T.LRList(depth=2),

            # unit types
            'v': T.LRValue(),
            'v[]': T.LRValue(''),
            'v[m/s]': T.LRValue('m/s'),
            'c': T.LRComplex(),
            'c[]': T.LRComplex(''),
            'c[m/s]': T.LRComplex('m/s'),

            # errors
            'E': T.LRError(),
            'Ew': T.LRError(T.LRWord()),
            'E(w)': T.LRError(T.LRCluster(T.LRWord())),

            # more complex stuff
            '*b*i': T.LRCluster(T.LRList(T.LRBool()), T.LRList(T.LRInt())),
        }
        for tag, type_ in tests.items():
            self.assertEqual(T.parseTypeTag(tag), type_)
            newtag = str(type_)
            if isinstance(type_, T.LRCluster) and tag[0] + tag[-1] != '()':
                # just added parentheses in this case
                self.assertEqual(newtag, '(%s)' % tag)
            else:
                self.assertEqual(newtag, tag)


    def testFlatAndBack(self):
        """Test roundtrip python->LabRAD->python conversion."""
        tests = [
            # simple types
            None,
            True, False,
            1, -1, 2, -2,
            1L, 2L, 3L, 4L,
            '', 'a', '\x00\x01\x02\x03',
            datetime.now(),

            # values
            5.0,
            T.Value(6, ''),
            T.Value(7, 'ms'),
            8+0j,
            T.Complex(9+0j, ''),
            T.Complex(10+0j, 'GHz'),

            # clusters
            (1, True, 'a'),
            ((1, 2), ('a', False)),

            # lists
            [],
            [1, 2, 3, 4],
            [1L, 2L, 3L, 4L],
            [[]],
            [['a', 'bb', 'ccc'], ['dddd', 'eeeee', 'ffffff']],

            # more complex stuff
            [(1L, 'a'), (2L, 'b')],
        ]
        for data_in in tests:
            #print data_in, T.flatten(data_in)
            data_out = T.unflatten(*T.flatten(data_in))
            self.assertEqual(data_in, data_out)

    def testTypeHints(self):
        """Test conversion to specified allowed types."""
        passingTests = [
            # convert to default type
            (1, [], 'i'),

            # convert to first compatible type
            (1, ['s', 'w'], 'w'),
            (1, ['s', 'v'], 'v'),
            (1*U.m, ['s', 'v[m]'], 'v[m]'),

            # empty list gets type from hint
            ([], ['s', '*(ww)'], '*(ww)'),
            
            # handle unknown pieces inside clusters and lists
            (['a', 'b'], ['*?'], '*s'),
            ((1, 2, 'a'), ['ww?'], 'wws'),
            ((1, 1L), ['??'], 'iw'),
        ]
        failingTests = [
            # no compatible types
            (5.0, ['s', 'b', 't', 'w', 'i'], 'v'),
        ]
        for data, hints, tag in passingTests:
            self.assertEqual(T.flatten(data, hints)[1], T.parseTypeTag(tag))
        for data, hints, tag in failingTests:
            self.assertRaises(T.FlatteningError, T.flatten, data, hints)

    def testTypeSpecialization(self):
        """Test specialization of the type during flattening."""
        tests = [
            # specialization without hints
            ([([],), ([5.0],)], '*(*v)'),
            ([([],), ([T.Value(5, 'm')],)], '*(*v[m])'),
        ]
        for data, tag in tests:
            self.assertEqual(T.flatten(data)[1], T.parseTypeTag(tag))
            
    def testUnitTypes(self):
        """Test flattening with units.
        
        The flattening code should not do unit conversion,
        but should leave that up to the LabRAD manager to handle.
        Basically, for purposes of flattening, a unit is a unit.
        """
        tests = [
            (T.Value(5.0, 'ft'), ['v[m]'], 'v[ft]'),
        ]
        for data, hints, tag in tests:
            self.assertEqual(T.flatten(data, hints)[1], T.parseTypeTag(tag))
    
    def testNumpySupport(self):
        """Test flattening and unflattening of numpy arrays"""
        import numpy as np
        
        # TODO: flesh this out with more array types
        a = np.array([1,2,3,4,5])
        b = T.unflatten(*T.flatten(a)).asarray
        self.assertTrue(np.all(a == b))
