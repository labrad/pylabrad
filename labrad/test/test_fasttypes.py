import pytest
import labrad.units as U
import numpy as np
import labrad.fasttypes as ft
import labrad.types as T

def check_flatten(data, expected_tag, expected_bytes):
    flatdata, tt = ft.flatten(data)
    assert tt==expected_tag
    assert len(flatdata)==expected_bytes

def test_int():
    assert ft.flatten(4) == ('\x00\x00\x00\x04', 'i')
    assert ft.flatten(4, 'i') == ('\x00\x00\x00\x04', 'i')
def test_str():
    assert ft.flatten('abcd', 's') == ('\x00\x00\x00\x04abcd', 's')
def test_simple():
    assert ft.flatten(None) == ('', '_')
    assert ft.flatten(True) == ('\x01', 'b')
    assert ft.flatten(False) == ('\x00', 'b')
    for x in [1, -1, 2, -2, 2**31-1, -2**31,
              '', 'a', '\x00\x01\x02\x03']:
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
def test_2d_string():
    check_flatten([['foo', 'bar'], ['abc', 'def'],['q', '1234']], '*2s', 49)
if __name__ == '__main__':
    pytest.main(['-v', __file__])
