import numpy as np
import labrad.units as U

tests = [
    # simple types
    None,
    True, False,
    1, -1, 2, -2, 2**31-1, -2**31,
    1L, 2L, 3L, 4L, 0L, 0xFFFFFFFFL,
    '', 'a', '\x00\x01\x02\x03',
    # datetime.now(),

    # values
    5.0,
    U.Value(6, ''),
    U.Value(7, 'ms'),
    8+0j,
    U.Complex(9+0j, ''),
    U.Complex(10+0j, 'GHz'),

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
    [(1L, 'a'), (2L, 'b')]
]

passcases = [ \
None, \
True, \
False, \
-3000000000, \
-2000000000, \
0, \
2000000000, \
3000000000, \
5000000000, \
-float('inf'), \
-1e308, \
0.0, \
1e308, \
float('inf'), \
1j, \
U.Value(1,'s'), \
U.Complex(1j,'s'), \
'abc', \
(None,), \
[], \
np.array([0,1,0],dtype=np.bool_), \
np.array([0,1,0],dtype=np.int32), \
np.array([0,1,0],dtype=np.uint32), \
np.array([0,1,0],dtype=np.float64), \
np.array([0,1,0],dtype=np.complex128), \
U.ValueArray(np.array([0,1,0],dtype=np.float64),'s'), \
U.ValueArray(np.array([0,1,0],dtype=np.complex128),'s'), \
[True, False, True], \
[0, 1, 2], \
[3000000000, 4000000000], \
[-1, -2, -3], \
[1.0, 2.0, 3.0], \
[1j, 2j, 3j], \
[U.Value(1,'s'), U.Value(2,'s')], \
[U.Complex(1j,'s'), U.Complex(2j,'s')], \
['abc', 'defgh'], \
[(None,), (None,)], \
[[], []], \
[np.array([0,1],dtype=np.int32), np.array([2,3,4],dtype=np.int32)], \
('a', 1, U.Value(1,'s'), True), \
[0, -1, 3000000000], \
[1, 1j], \
[([],),([1],),([-1],),([3000000000],)], \
[([],[0]),([1],[]),([-1],[5000000000]),([3000000000],[])], \
[np.eye(2,2),np.eye(3,3)], \
[np.eye(2,2),np.eye(3,3),[[1,2]],[]], \
[U.Value(1,'s'),U.Complex(3-7j,'s')]
]

"""
-3000000000, \
-2000000000, \
1, \
1000000000, \
3000000000, \
5000000000, \
0., \
0j, \
1., \
1+1j, \
'a', \
'abc', \
True, \
False, \
1.*U.ns, \
1j*U.ms, \
[], \
[1], \
[3000000000], \
[0.], \
[0j], \
[1.], \
[1+1j], \
['a'], \
['abc'], \
[True], \
[False], \
[1.*U.ns], \
[1j*U.ms], \
(), \
(1,), \
(3000000000,), \
(0.,), \
(0j,), \
(1.,), \
(1+1j,), \
('a',), \
('abc',), \
(True,), \
(False,), \
(1.*U.ns,), \
(1j*U.ms,), \
[1,2,3], \
[1000000000,2000000000,3000000000], \
[1.0,2.0,3.0], \
[1j,2j,3j], \
['a','b','c'], \
['aaa','bbb','ccc'], \
[True,False,True], \
[1.*U.ns,2.*U.ns,3.*U.ns], \
[1j*U.ms,2j*U.ms,3j*U.ms], \
[([1],[1]),([1],[1])], \
[([],[1]),([1],[1])], \
[([1],[]),([1],[1])], \
[([1],[1]),([],[1])], \
[([1],[1]),([1],[])],
[[1,2,3],[],[2,3,3000000000,5]],
[1, 1.0, 1j] \
]
"""