from __future__ import absolute_import

from concurrent.futures import Future
import pytest

from labrad.concurrent import MutableFuture


def test_mutable_future():
    f = Future()
    mf = MutableFuture(f)
    f.set_result(1)
    assert mf.result() == 1


def test_mutable_future_on_already_completed_future():
    f = Future()
    f.set_result(1)
    mf = MutableFuture(f)
    assert mf.result() == 1


if __name__ == '__main__':
    pytest.main(['-v', __file__])
