import pytest
import labrad.units as U
import labrad.fasttypes as ft
import labrad.types as T

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
def test_list():
    assert all(T.unflatten(*ft.flatten([1,2,3])) == [1,2,3])
    (data, tt) = T.flatten([1,2,3])
    data, tt = str(data), str(tt)
    assert all(ft.unflatten((data, tt)) == [1,2,3])
    assert len(ft.flatten(['a', 'bc', 'def'])[0])==22
def test_list_w_tag():
    assert str(ft.flatten(['a', 'bc', 'def'])[1])=='*s'
    assert ft.flatten([1,2,3]) == ft.flatten([1,2,3], '*i')

if __name__ == '__main__':
    pytest.main(['-v', __file__])
