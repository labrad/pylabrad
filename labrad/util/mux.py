from twisted.internet import defer

from labrad import util


def after(delay):
    """Return a Deferred that will fire after the given delay (in seconds).

    This can be useful to implement a "timeout" option when calling select.
    """
    return util.wakeupCall(delay)


def select(options):
    """Select from among a set of Deferreds the first one that fires.

    Args:
        options (Dict[str, Deferred]): Map from key name (str) to Deferred. The
            key associated with the first Deferred that fires will be returned
            in the resulting Selection to identify which one fired.

    Returns:
        (Deferred[Selection]): A Deferred that will fire with a Selection that
        contains the key of the selected Deferred and the resulting value or
        error.
    """
    result = defer.Deferred()
    @defer.inlineCallbacks
    def handle(key, deferred):
        try:
            value = yield deferred
            try:
                result.callback(Selection(key, value))
            except defer.AlreadyCalledError:
                pass
        except Exception as e:
            try:
                result.callback(Selection(key, error=e))
            except defer.AlreadyCalledError:
                pass
    for key, deferred in options.items():
        handle(key, deferred)
    return result


class Selection(object):
    """The result of the first firing Deferred from a call to select."""
    def __init__(self, key, result=None, error=None):
        self.key = key
        self._result = result
        self._error = error

    def result(self):
        """Get the result (or raise the error) from the selected Deferred."""
        if self._error is not None:
            raise self._error
        return self._result
