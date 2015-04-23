import pytest
import labrad.units as U
import labrad.fasttypes as ft
import labrad.types as T

def test_int():
    assert ft.flatten(4) == ('\x00\x00\x00\x04', 'i')
    assert ft.flatten(4, 'i') == ('\x00\x00\x00\x04', 'i')
def test_str():
    assert ft.flatten('abcd', 's') == ('\x00\x00\x00\x04abcd', 's')
def test_wrong_type():
    with pytest.raises(Exception):
        ft.flatten('abcd', 'i')
    with pytest.raises(Exception):
        ft.flatten(4, 's')
def test_list():
    assert all(T.unflatten(*ft.flatten([1,2,3])) == [1,2,3])
    assert all(ft.unflatten(T.flatten([1,2,3])) == [1,2,3])
    assert ft.flatten([1,2,3]) == ft.flatten([1,2,3], '*i')
if __name__ == '__main__':
    pytest.main(['-v', __file__])
