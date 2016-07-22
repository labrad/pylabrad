from __future__ import absolute_import

from concurrent.futures import Future
import pytest

from labrad.concurrent import map_future


def test_map_future():
    f = Future()
    mf = map_future(f, lambda x: x + 1)
    f.set_result(1)
    assert mf.result() == 2


def test_map_future_on_already_completed_future():
    f = Future()
    f.set_result(1)
    mf = map_future(f, lambda x: x + 1)
    assert mf.result() == 2


if __name__ == '__main__':
    pytest.main(['-v', __file__])
