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
        self.__src = src

    def cancel(self):
        return super(MappedFuture, self).cancel() and self.__src.cancel()

