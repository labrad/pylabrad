from __future__ import absolute_import

from concurrent.futures import Future
from twisted.internet import defer, reactor
from twisted.python import threadable
import pytest

import labrad.concurrent as concurrent
import labrad.thread as thread


def test_map_future():
    f = Future()
    mf = concurrent.map_future(f, lambda x: x + 1)
    f.set_result(1)
    assert mf.result() == 2


def test_map_future_on_already_completed_future():
    f = Future()
    f.set_result(1)
    mf = concurrent.map_future(f, lambda x: x + 1)
    assert mf.result() == 2


class TestCallFuture(object):
    """Test call_future function, which wraps twisted code in a Future."""

    @classmethod
    def setup_class(cls):
        # make sure twisted reactor is running
        thread.startReactor()

    def test_synchronous_func(self):
        def func():
            return threadable.isInIOThread()

        f = concurrent.call_future(func)
        assert f.result(timeout=0.1)

    def test_synchronous_error(self):
        def func():
            raise ValueError()

        f = concurrent.call_future(func)
        with pytest.raises(ValueError):
            f.result(timeout=0.1)

    def test_asynchronous_func(self):
        @defer.inlineCallbacks
        def func():
            d = defer.Deferred()
            reactor.callLater(0, d.callback, 'woot')
            result = yield d
            defer.returnValue(result)

        f = concurrent.call_future(func)
        assert f.result(timeout=0.1) == 'woot'

    def test_asynchronous_error(self):
        @defer.inlineCallbacks
        def func():
            d = defer.Deferred()
            reactor.callLater(0, d.callback, 'woot')
            result = yield d
            raise ValueError()

        f = concurrent.call_future(func)
        with pytest.raises(ValueError):
            f.result(timeout=0.1)


class TestFutureToDeferred(object):
    """Test future_to_deferred which wraps a Future in a twisted Deferred."""

    @classmethod
    def setup_class(cls):
        # make sure twisted reactor is running
        thread.startReactor()

    def test_result_already_set(self):
        @defer.inlineCallbacks
        def func(f):
            result = yield concurrent.future_to_deferred(f)
            defer.returnValue(result)

        f1 = Future()
        f1.set_result(1)
        f2 = concurrent.call_future(func, f1)
        assert f2.result(timeout=0.1) == 1

    def test_set_result_outside_reactor(self):
        @defer.inlineCallbacks
        def func(f):
            result = yield concurrent.future_to_deferred(f)
            defer.returnValue(result)

        f1 = Future()
        f2 = concurrent.call_future(func, f1)
        f1.set_result(1)
        assert f2.result(timeout=0.1) == 1

    def test_set_result_inside_reactor(self):
        @defer.inlineCallbacks
        def func(f):
            d = concurrent.future_to_deferred(f)
            f.set_result(1)
            result = yield d
            defer.returnValue(result)

        f = Future()
        future = concurrent.call_future(func, f)
        assert future.result() == 1

    def test_exception_already_set(self):
        @defer.inlineCallbacks
        def func(f):
            result = yield concurrent.future_to_deferred(f)
            defer.returnValue(result)

        f1 = Future()
        f1.set_exception(ValueError())
        f2 = concurrent.call_future(func, f1)
        with pytest.raises(ValueError):
            f2.result(timeout=0.1)

    def test_set_exception_outside_reactor(self):
        @defer.inlineCallbacks
        def func(f):
            result = yield concurrent.future_to_deferred(f)
            defer.returnValue(result)

        f1 = Future()
        f2 = concurrent.call_future(func, f1)
        f1.set_exception(ValueError())
        with pytest.raises(ValueError):
            f2.result(timeout=0.1)

    def test_set_result_inside_reactor(self):
        @defer.inlineCallbacks
        def func(f):
            d = concurrent.future_to_deferred(f)
            f.set_exception(ValueError())
            result = yield d
            defer.returnValue(result)

        f = Future()
        future = concurrent.call_future(func, f)
        with pytest.raises(ValueError):
            future.result()


if __name__ == '__main__':
    pytest.main(['-v', __file__])
