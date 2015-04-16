import concurrent.futures

def transform(future, fn):
    """Transform a future by applying a function to its result.

    Args:
        future: A concurrent.futures.Future to be transformed
        fn: The function to apply to the result of future.

    Returns:
        A concurrent.future.Future whose result will be fn
        applied to the result of the input future. If the input
        fails, this future will fail with the same exception.
        If calling fn on the result raises an exception, this
        future will fail with that exception.
    """
    new = concurrent.futures.Future()
    def chain(old):
        e = old.exception()
        if e is not None:
            new.set_exception(e)
        else:
            try:
                old_result = old.result()
                new_result = fn(old_result)
                new.set_result(new_result)
            except Exception as e:
                new.set_exception(e)
    future.add_done_callback(chain)
    return new
