import pytest
import labrad.units as U
import numpy as np
import labrad.fasttypes as ft
import time
import labrad.types as T
import datetime as dt

def check_flatten(data, expected_tag, expected_bytes):
    flatdata, tt = ft.flatten(data)
    assert tt==expected_tag
    assert len(flatdata)==expected_bytes

def roundtrip(obj, tag=None):
    if tag:
        flatdata, tt = ft.flatten(obj, tag)
    else:
        flatdata, tt = ft.flatten(obj)
    
    output = ft.unflatten((flatdata, tt))
    return output

def check_roundtrip(obj, tag=None, result=None):
    output = roundtrip(obj, tag)
    if result:
        assert output==result
    else:
        assert output==obj

def check_array_roundtrip(obj, tag=None, result=None):
    output = roundtrip(obj, tag)
    if result:
        assert np.array_equal(output, result)
    else:
        assert np.array_equal(output, obj)
    
def test_int():
    assert ft.flatten(4) == ('\x00\x00\x00\x04', 'i')
    assert ft.flatten(4, 'i') == ('\x00\x00\x00\x04', 'i')
def test_str():
    assert ft.flatten('abcd', 's') == ('\x00\x00\x00\x04abcd', 's')
def test_simple():
    assert ft.flatten(None) == ('', '_')
    assert ft.flatten(True) == ('\x01', 'b')
    assert ft.flatten(False) == ('\x00', 'b')
    # for x in [1, -1, 2, -2, 2**31-1, -2**31,
    for x in [1, -1, 2, -2,
              '', 'a', '\x00\x01\x02\x03']:
        print x
        assert ft.flatten(x)[0] == T.flatten(x)[0]
        assert ft.flatten(x)[1] == str(T.flatten(x)[1])

def test_wrong_type(): # Figure out the right exceptions to use here
    with pytest.raises(Exception):
        ft.flatten('abcd', 'i')
    with pytest.raises(Exception):
        ft.flatten(4, 's')
def test_multiple_types():
    assert ft.flatten(32, ['s', 'i', 'v[]'])[1] == 'i'
def test_list():
    assert all(T.unflatten(*ft.flatten([1,2,3])) == [1,2,3])
    (data, tt) = T.flatten([1,2,3])
    data, tt = str(data), str(tt)
    assert all(ft.unflatten((data, tt)) == [1,2,3])
    assert len(ft.flatten(['a', 'bc', 'def'])[0])==22
def test_cluster_data():
    data = ('abc', 1)
    assert ft.flatten(data)[0] == T.flatten(data)[0]
def test_cluster_tag():
    assert ft.flatten((1, 'abc', 3.2))[1] == '(isv[])'
def test_list_w_tag():
    assert str(ft.flatten(['a', 'bc', 'def'])[1])=='*s'
    assert ft.flatten([1,2,3]) == ft.flatten([1,2,3], '*i')
def test_values():
    assert ft.flatten(3.2)[1] == 'v[]'
    assert ft.flatten(3.2*U.ns)[1] == 'v[ns]'
    assert ft.flatten(3+4j)[1] == 'c[]'
    assert ft.flatten(4j*U.V)[1] == 'c[V]'
def test_float_list():
    check_flatten([1.0, 2.0, 3.0],'*v[]', 8*3+4)
def test_float_list_tt():
    ft.flatten([1.0, 2.0, 3.0], '*v[]')[1] == '*v[]'
def test_ndarray():
    check_flatten(np.arange(3)*1.5, '*v[]', 8*3+4)
def test_ndarray_tt():
    assert ft.flatten(np.arange(3)*1.5, '*v[]')[1] == '*v[]'
def test_value_array():
    check_flatten(np.arange(10)*U.ns, '*v[ns]', 10*8+4)
def test_value_array_tt():
    assert ft.flatten(np.arange(10)*U.ns, '*v[ns]')[1] == '*v[ns]'
def test_cluster_list():
    assert ft.flatten([('foo', 123), ('bar', 42)])[1] == '*(si)'
def test_illegal_typetag():
    with pytest.raises(SyntaxError):
        ft.flatten(1, 'q')
def test_illegal_listtag():
    with pytest.raises(SyntaxError):
        ft.flatten(1, '*q')
def test_2d_ndarray():
    check_flatten(np.eye(4), '*2v[]', 16*8+2*4)
def test_2d_valuearray():
    check_flatten(np.eye(4)*U.ns, '*2v[ns]', 16*8+2*4)
def test_2d_list():
    check_flatten([[1, 0], [0, 1]], '*2i', 4*6)
def test_2d_mixed_unit():
    with pytest.raises(TypeError):
        ft.flatten([1*U.m, 2*U.ns])
def test_2d_string():
    check_flatten([['foo', 'bar'], ['abc', 'def'],['q', '1234']], '*2s', 49)
def test_ragged_list():
    with pytest.raises(TypeError):
        data, tt = ft.flatten([[1,2,3], [4,5]])
    with pytest.raises(TypeError):
        data, tt = ft.flatten([['foo', 'bar'], ['baz']])
@pytest.mark.xfail(raises=TypeError)
def test_datetime():
    data, tt = ft.flatten(dt.datetime(2004,1,1))
    assert tt == 't'
    (secs, frac_secs) = struct.unpack('>qQ', data)
    assert abs(1 - secs / 3.141e9) < .005 # If we are this close it is probably right
                                          # but we don't check exactly because of timezone offsets
@pytest.mark.xfail(raises=TypeError)
def test_datetime_negative():
    # This is the offset used by the python types.py to convert
    # datetime objects presumed to have the current local time offset
    # into UTC.  Note that this is not necessarily legit.
    now = time.time()
    offset = dt.datetime.fromtimestamp(now) - dt.datetime.utcfromtimestamp(now)
    data, tt = ft.flatten(dt.datetime(1904, 1, 1) + offset - dt.timedelta(seconds=1, milliseconds=500))
    assert tt == 't'
    (secs, frac_secs) = struct.unpack('>qQ', data)
    assert secs == -2
    assert frac_secs == 2**63

def test_rt_basic():
    check_roundtrip(0)
    check_roundtrip('foo bar')
    check_roundtrip(42.0)
    check_roundtrip(1.21*U.GW)
    check_roundtrip(True)
    check_roundtrip(False)
    check_roundtrip(None)
    check_roundtrip(3.1415+2.718j)

def test_rt_cluster():
    check_roundtrip((1,'foo', True))

def test_rt_array():
    check_array_roundtrip(np.arange(5)*U.ns)
    check_array_roundtrip(np.eye(4))
    check_array_roundtrip([1, 2, 3])
    
def test_rt_list():
    check_roundtrip(['foo', 'bar'])
    check_roundtrip([['foo', 'bar'], ['baz', '12345']])

def test_unflatten_short_str():
    data, tt = ft.flatten('foobar')
    with pytest.raises(ValueError):
        ft.unflatten((data[0:3], tt))
    with pytest.raises(ValueError):
        ft.unflatten((data[0:8], tt))

def test_unflatten_short_array():
    obj = np.array(np.eye(5))
    data, tt = ft.flatten(obj)
    with pytest.raises(ValueError):
        ft.unflatten((data[0:3], tt))
    with pytest.raises(ValueError):
        ft.unflatten((data[0:6], tt))
    with pytest.raises(ValueError):
        ft.unflatten((data[0:14], tt))

if __name__ == '__main__':
    pytest.main(['-v', __file__])
