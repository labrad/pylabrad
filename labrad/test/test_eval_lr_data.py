import math

import pytest

import labrad.types as T
from labrad.units import Complex, Value


def test_eval_value_with_none_for_units():
    assert T.evalLRData("""Value(1.0, None)""") == Value(1.0, '')


def test_eval_complex_with_none_for_units():
    assert T.evalLRData("""Complex(1.1, None)""") == Complex(1.1, '')


def test_eval_cluster_with_value_and_complex():
    assert (T.evalLRData("""(Value(1.0, None), Complex(2.0, None))""") ==
            (Value(1.0, ''), Complex(2.0, '')))


def test_eval_nan():
    s = T.reprLRData(float('nan'))
    n = T.evalLRData(s)
    assert math.isnan(n)

    s2 = T.reprLRData((float('nan'), 'this is a test'))
    n2, _ = T.evalLRData(s2)
    assert math.isnan(n2)


def test_eval_positive_infinity():
    s = T.reprLRData(float('inf'))
    n = T.evalLRData(s)
    assert math.isinf(n)
    assert n > 0

    s2 = T.reprLRData((float('inf'), 'this is a test'))
    n2, _ = T.evalLRData(s2)
    assert math.isinf(n2)
    assert n2 > 0


def test_eval_negative_infinity():
    s = T.reprLRData(float('-inf'))
    n = T.evalLRData(s)
    assert math.isinf(n)
    assert n < 0

    s2 = T.reprLRData((float('-inf'), 'this is a test'))
    n2, _ = T.evalLRData(s2)
    assert math.isinf(n2)
    assert n2 < 0


if __name__ == '__main__':
    pytest.main(['-v', __file__])
