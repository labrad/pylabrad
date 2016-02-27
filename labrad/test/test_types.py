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
import numpy as np

import sys
import os
sys.path.insert(0, os.path.abspath('../..'))

import labrad.types as T
import labrad.units as U

from labrad.units import Value, ValueArray, Complex


class LabradTypesTests(unittest.TestCase):

    def testTags(self):
        """Test the parsing of type tags into LRType objects."""
        tests = {
            '_': T.LRNone(),
            'b': T.LRBool(),
            'i': T.LRInt(),
            'w': T.LRWord(),
            's': T.LRStr(),
            't': T.LRTime(),
            'y': T.LRBytes(),

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
            '*2v[Hz]': T.LRList(T.LRValue('Hz'), depth=2),
            '*3v': T.LRList(T.LRValue(), depth=3),
            '*v[]': T.LRList(T.LRValue(''), depth=1),

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

    def testTagComments(self):
        """Test the parsing of type tags with comments and whitespace."""
        tests = {
            '': T.LRNone(),
            ' ': T.LRNone(),
            ': this is a test': T.LRNone(),
            '  : this is a test': T.LRNone(),
            '   i  ': T.LRInt(),
            '   i  :': T.LRInt(),
            '   i  : blah': T.LRInt(),
        }
        for tag, type_ in tests.items():
            self.assertEqual(T.parseTypeTag(tag), type_)

    def testDefaultFlatAndBack(self):
        """
        Test roundtrip python->LabRAD->python conversion.

        No type requirements are given in these tests. In other words, we allow
        pylabrad to choose a default type for flattening.

        In this test, we expect A == unflatten(*flatten(A)). In other words,
        we expect the default type chosen for each object to unflatten as
        an object equal to the one originally flattened.
        """
        tests = [
            # simple types
            None,
            True, False,
            1, -1, 2, -2, 0x7FFFFFFF, -0x80000000,
            1L, 2L, 3L, 4L, 0L, 0xFFFFFFFFL,
            '', 'a', '\x00\x01\x02\x03',
            datetime.now(),

            # values
            5.0,
            Value(6, ''),
            Value(7, 'ms'),
            8+0j,
            Complex(9+0j, ''),
            Complex(10+0j, 'GHz'),

            # ValueArray and ndarray
            # These types should be invariant under flattening followed by
            # unflattening. Note, however, that since eg. [1, 2, 3] will
            # unflatten as ndarray with dtype=int32, we do not put lists
            # in this test.
            U.ValueArray([1, 2, 3], 'm'),
            U.ValueArray([1j, 2j, 3j], 's'),
            np.array([1, 3, 4], dtype='int32'),
            np.array([1.1, 2.2, 3.3]),

            # clusters
            (1, True, 'a'),
            ((1, 2), ('a', False)),

            # lists
            [],
            #[1, 2, 3, 4],
            #[1L, 2L, 3L, 4L],
            [[]],
            [['a', 'bb', 'ccc'], ['dddd', 'eeeee', 'ffffff']],

            # more complex stuff
            [(1L, 'a'), (2L, 'b')],
        ]
        for data_in in tests:
            data_out = T.unflatten(*T.flatten(data_in))
            if isinstance(data_in, U.ValueArray):
                self.assertTrue(data_in.allclose(data_out))
            elif isinstance(data_in, np.ndarray):
                np.testing.assert_array_equal(data_out, data_in)
            else:
                self.assertEqual(data_in, data_out)

    def testDefaultFlatAndBackNonIdentical(self):
        """
        Test flattening/unflattening of objects which change type.

        No type requirements are given in these tests. In other words, we allow
        pylabrad to choose a default type for flattening.

        In this test, we do not expect A == unflatten(*flatten(A)). This is
        mostly because list of numbers, both with an without units, should
        unflatten to ndarray or ValueArray, rather than actual python lists.
        """
        def compareValueArrays(a, b):
            """I check near equality of two ValueArrays"""
            self.assertTrue(a.allclose(b))

        tests = [
            ([1, 2, 3], np.array([1, 2, 3], dtype='int32'),
                np.testing.assert_array_equal),
            ([1.1, 2.2, 3.3], np.array([1.1, 2.2, 3.3], dtype='float64'),
                np.testing.assert_array_almost_equal),
            (np.array([3, 4], dtype='int32'), np.array([3, 4], dtype='int32'),
                np.testing.assert_array_equal),
            (np.array([1.2, 3.4]), np.array([1.2, 3.4]),
                np.testing.assert_array_almost_equal),
            ([Value(1.0, 'm'), Value(3.0, 'm')], ValueArray([1.0, 3.0], 'm'),
                compareValueArrays),
            ([Value(1.0, 'm'), Value(10, 'cm')], ValueArray([1.0, 0.1], 'm'),
                compareValueArrays),
            (ValueArray([1, 2], 'Hz'), ValueArray([1, 2], 'Hz'),
                compareValueArrays),
            (ValueArray([1.0, 2], ''), np.array([1.0, 2]),
                np.testing.assert_array_almost_equal),
            # Numpy scalar types
            (np.bool8(True), True, self.assertEqual) 
        ]
        for input, expected, comparison_func in tests:
            unflat = T.unflatten(*T.flatten(input))
            if isinstance(unflat, np.ndarray):
                self.assertEqual(unflat.dtype, expected.dtype)
            comparison_func(unflat, expected)

    def testFlatAndBackWithTypeRequirements(self):
        tests = [
            ([1, 2, 3], ['*i'], np.array([1, 2, 3]),
                np.testing.assert_array_equal),
            ([1, 2], ['*v[]'], np.array([1, 2]),
                np.testing.assert_array_almost_equal),
            ([1.1, 2.], ['*v[]'], np.array([1.1, 2.], dtype='float64'),
                np.testing.assert_array_almost_equal)
        ]
        for input, types, expected, comparison_func in tests:
            flat = T.flatten(input, types)
            unflat = T.unflatten(*flat)
            comparison_func(expected, unflat)

    def testBooleanArrayFlattening(self):
        flat = T.flatten([True, False, True])
        unflat = T.unflatten(*flat)
        flat2 = T.flatten(unflat)
        unflat2 = T.unflatten(*flat2)
        np.testing.assert_array_equal(unflat, unflat2)

    def testFailedFlattening(self):
        """
        Trying to flatten data to an incompatible type should raise an error.
        """
        cases = [
            # Simple cases
            (1, ['s', 'v[Hz]']),
            ('X', ['i', 'v', 'w']),
            (5.0, ['s', 'b', 't', 'w', 'i', 'v[Hz]']),
            # Value
            (5.0, 'v[Hz]'),
            (Value(4, 'm'), 'v[]'),
            (Value(3, 's'), ['v[Hz]', 'i', 'w']),
            # ndarray
            (np.array([1, 2, 3], dtype='int32'), '*v[Hz]'),
            (np.array([1.0, 2.4]), ['*i', '*w']),
            # ValueArray
            (U.ValueArray([1, 2, 3], 'm'), '*v[s]'),
            (U.ValueArray([1, 2], 'm'), '*v[]')
        ]
        for data, targetTag in cases:
            self.assertRaises(T.FlatteningError, T.flatten, data, targetTag)

    def testTypeHints(self):
        """Test conversion to specified allowed types."""
        passingTests = [
            # convert to default type
            (1, [], 'i'),

            # convert to first compatible type
            (1, ['s', 'w'], 'w'),
            (1, ['s', 'v'], 'v[]'),
            (1*U.m, ['s', 'v[m]'], 'v[m]'),
            # 'v' not allowed on wire
            (3.0, 'v', 'v[]'),
            (3, 'v', 'v[]'),

            # empty list gets type from hint
            ([], ['s', '*(ww)'], '*(ww)'),

            # handle unknown pieces inside clusters and lists
            (['a', 'b'], ['*?'], '*s'),
            ((1, 2, 'a'), ['ww?'], 'wws'),
            ((1, 1L), ['??'], 'iw'),
        ]
        for data, hints, tag in passingTests:
            self.assertEqual(T.flatten(data, hints)[1], T.parseTypeTag(tag))

    def testTypeSpecialization(self):
        """Test specialization of the type during flattening."""
        tests = [
            # specialization without hints
            ([([],), ([5.0],)], '*(*v)'),
            ([([],), ([Value(5, 'm')],)], '*(*v[m])'),
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
            (Value(5.0, 'ft'), ['v[m]'], 'v[ft]'),

            # real value array
            (U.ValueArray([1, 2, 3], ''), [], '*v[]'),
            (U.ValueArray([1, 2, 3], 'm'), ['*v[m]'], '*v[m]'),

            # complex value array
            (U.ValueArray([1j, 2j, 3j], ''), [], '*c[]'),
            (U.ValueArray([1j, 2j, 3j], 'm'), [], '*c[m]')
        ]
        for data, hints, tag in tests:
            self.assertEqual(T.flatten(data, hints)[1], T.parseTypeTag(tag))

        # we disallow flattening a float to a value with units,
        # as this is a major source of bugs
        try:
            T.flatten(5.0, 'v[m]')
        except Exception:
            pass
        else:
            raise Exception('Cannot flatten float to value with units')

    def testNumpySupport(self):
        """Test flattening and unflattening of numpy arrays"""
        import numpy as np

        # TODO: flesh this out with more array types
        a = np.array([1, 2, 3, 4, 5], dtype='int32')
        b = T.unflatten(*T.flatten(a))
        self.assertTrue(np.all(a == b))
        self.assertTrue(T.flatten(np.int32(5))[0] == '\x00\x00\x00\x05')
        self.assertTrue(T.flatten(np.int64(-5))[0] == '\xff\xff\xff\xfb')
        self.assertTrue(len(T.flatten(np.float64(3.15))[0]) == 8)
        with self.assertRaises(T.FlatteningError):
            T.flatten(np.int64(-5), T.LRWord())

    def testIntegerRanges(self):
        """Test flattening of out-of-range integer values"""
        tests = [
            (0x80000000, 'i'),
            (-0x80000001, 'i'),
            (0x100000000, 'w'),
            (-1, 'w')
        ]
        for n, t in tests:
            with self.assertRaises(T.FlatteningError):
                T.flatten(n, t)

    def testFlattenIsIdempotent(self):
        flat = T.flatten(0x1, 'i')
        self.assertEquals(T.flatten(flat), flat)
        self.assertEquals(T.flatten(flat, 'i'), flat)
        with self.assertRaises(T.FlatteningError):
            T.flatten(flat, 'v')

    def testEvalDatetime(self):
        data = datetime.now()
        data2 = T.evalLRData(repr(data))
        self.assertEquals(data, data2)

    def testUnicodeBytes(self):
        foo = T.flatten('foo bar')
        self.assertEquals(foo, T.flatten(u'foo bar'))
        self.assertEquals(str(foo.tag), 's')
        self.assertEquals(T.unflatten(foo.bytes, 'y'), 'foo bar')
        self.assertEquals(T.unflatten(*T.flatten('foo bar', ['y'])), 'foo bar')

    def testFlattenIntArrayToValueArray(self):
        x = np.array([1, 2, 3, 4], dtype='int64')
        flat = T.flatten(x, '*v')
        y = T.unflatten(*flat)
        self.assertTrue(np.all(x == y))

    def testCanFlattenFlatData(self):
        x = ('this is a test', -42, [False, True])
        flat = T.flatten(x)
        self.assertEquals(T.parseTypeTag(flat.tag), T.parseTypeTag('si*b'))
        flat2 = T.flatten(x)
        self.assertEquals(flat2, flat)
        flat3 = T.flatten(x, 'si*b')
        self.assertEquals(flat3, flat)
        with self.assertRaises(T.FlatteningError):
            T.flatten(x, 'sv')

    def testCanFlattenListOfPartialFlatData(self):
        x1 = ('this is a test', -42, [False, True])
        piece1 = T.flatten(x1)
        x2 = ('this is also a test', -43, [False, True, True, True])
        piece2 = T.flatten(x2)

        not_flattened = [x1, x2]
        partially_flattened = [piece1, piece2]
        tag = '*(si*b)'

        expected = T.flatten(not_flattened)

        flat1 = T.flatten(partially_flattened)
        self.assertEquals(flat1, expected)

        flat2 = T.flatten(partially_flattened, tag)
        self.assertEquals(flat2, expected)

        with self.assertRaises(T.FlatteningError):
            T.flatten(partially_flattened, '*(si)')

    def testCanFlattenClusterOfPartialFlatData(self):
        x1 = ('this is a test', -42, [False, True])
        piece1 = T.flatten(x1)
        x2 = ('this is also a test', -43, [False, True, True, True])
        piece2 = T.flatten(x2)

        not_flattened = (('1', x1), ('2', x2, False))
        partially_flattened = (('1', piece1), ('2', piece2, False))
        tag = '((s(si*b)) (s(si*b)b))'

        expected = T.flatten(not_flattened)

        flat1 = T.flatten(partially_flattened)
        self.assertEquals(flat1, expected)

        flat2 = T.flatten(partially_flattened, tag)
        self.assertEquals(flat2, expected)

        with self.assertRaises(T.FlatteningError):
            T.flatten(partially_flattened, '*(s(si*b))')


if __name__ == "__main__":
    unittest.main()
