from __future__ import absolute_import

from concurrent import futures
from twisted.internet import defer, reactor


def map_future(src, func, *args, **kw):
    """Create a future that applies a function to the result of a source future.

    Args:
        src (concurrent.futures.Future): The future whose result we wish to
            modify.
        func (callable): Function to apply to the result of src. This function
            will be called like func(result, *args, **kw) where result is the
            value produced by src.
        args: Positional args to be passed to func.
        kw: Keyword args to be passed to func.

    Returns:
        A new Future whose result will be the given function applied to the
        result of src. If src fails with an exception, or if func raises an
        exception when called, the error will be propagated to the returned
        future.
    """
    return MappedFuture(src, func, *args, **kw)


class MappedFuture(futures.Future):
    """A Future that receives the result or failure of another Future.

    Args:
        src (concurrent.future.Future): Source future whose value this future
            will receive and possibly modify.
        func (callable | None): Function that will be applied to the result of
            src before setting it on this Future. This function will be called
            like func(result, *args, **kw). If None, the result will be passed
            along unchanged.
        args: Positional args to be passed to func.
        kw: Keyword args to be passed to func.
    """
    def __init__(self, src, func, *args, **kw):
        super(MappedFuture, self).__init__()
        def handle_result(f):
            if not self.set_running_or_notify_cancel():
                return
            if src.cancelled():
                self.set_exception(futures.CancelledError())
                return
            error = src.exception()
            if error is not None:
                self.set_exception(error)
                return
            try:
                result = src.result()
                if func is not None:
                    result = func(result, *args, **kw)
                self.set_result(result)
            except Exception as e:
                self.set_exception(e)
        src.add_done_callback(handle_result)
        self.__src = src

    def cancel(self):
        return super(MappedFuture, self).cancel() and self.__src.cancel()


def call_future(func, *args, **kw):
    """Run func in the twisted reactor thread; return the result as a Future.

    Args:
        func (callable): Function to be run in the twisted reactor thread. May
            return a Deferred.
        *args: Positional arguments to pass to func.
        **kw: Keyword arguments to pass to func.

    Returns:
        (concurrent.future.Future) Future that will receive the result of
        calling func or an exception if it fails.
    """
    f = futures.Future()
    @defer.inlineCallbacks
    def wrapped():
        try:
            result = yield defer.maybeDeferred(func, *args, **kw)
            f.set_result(result)
        except Exception as e:
            f.set_exception(e)
    reactor.callFromThread(wrapped)
    return f


def future_to_deferred(future):
    """Create a twisted Deferred from a Future.

    Args:
        future (concurrent.future.Future): Future whose result or failure we
            wish to capture in a deferred.

    Returns:
        (twisted.internet.defer.Deferred) that will fire when the future
        completes with a result (callback) or error (errback).
    """
    deferred = defer.Deferred()
    def handle_result(future):
        if future.cancelled():
            reactor.callFromThread(deferred.errback, futures.CancelledError())
            return
        error = future.exception()
        if error is not None:
            reactor.callFromThread(deferred.errback, error)
            return
        result = future.result()
        reactor.callFromThread(deferred.callback, result)
    future.add_done_callback(handle_result)
    return deferred

