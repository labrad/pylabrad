from __future__ import absolute_import

import warnings

from concurrent import futures


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
        self._src = src

    def cancel(self):
        return super(MappedFuture, self).cancel() and self._src.cancel()


class MutableFuture(MappedFuture):
    """Backwards compatible subclass of concurrent.futures.Future.

    The biggest difference from standard Futures is that the old labrad Future
    tries to emulate the mutable addCallback interface of twisted Deferreds. To
    emulate this behavior, we keep a list of callback functions which are used
    to transform the result of the future when .result() is called.

    We also provide .wait() as an alias for .result(), since the old Future
    class used the former to get value.

    Note: this class will be removed after users have updated to use the
        standard Future interface with mapping.
    """
    def __init__(self, source):
        super(MutableFuture, self).__init__(source, None)
        self._callbacks = []
        self._done = False
        self._result = None
        self._error = None

    def addCallback(self, func, *args, **kw):
        warnings.warn("addCallback is deprecated; use map_future instead.")
        self._callbacks.append((func, args, kw))

    def wait(self):
        """Alias for the result() method; for backwards compatibility."""
        warnings.warn(".wait() is deprecated; use .result() instead.")
        return self.result()

    def result(self, timeout=None):
        if not self._done:
            self._result = super(MutableFuture, self).result(timeout)
            self._done = True
        if self._error is not None:
            raise self._error
        while len(self._callbacks):
            func, args, kw = self._callbacks.pop(0)
            try:
                self._result = func(self._result, *args, **kw)
            except Exception as e:
                self._error = e
                raise e
        return self._result

    def exception(self, timeout=None):
        if not self._done:
            self._error = super(MutableFuture, self).exception(timeout)
            self._done = True
        return self._error
