from twisted.internet import defer

from labrad import util


def select(**kwargs):
    """Select from among a set of Deferreds the first one that fires.

    Args:
        **kwargs: Map from key name (str) to Deferred. The key associated with
            the first Deferred that fires will be returned in the resulting
            Selection to identify which one fired. In addition to Deferreds,
            the special keyword arg 'timeout' can be specified as a number
            giving a timeout in seconds. This will cause the selection to
            timeout if none of the other provided Deferreds fire before the
            specified time elapses.

    Returns:
        (Deferred[Selection]): A Deferred that will fire with a Selection that
        contains the key of the selected Deferred and the resulting value or
        error.
    """
    if 'timeout' in kwargs:
        kwargs['timeout'] = util.wakeupCall(kwargs['timeout'])
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
    for key, deferred in kwargs.items():
        handle(key, deferred)
    return result


class Selection(object):
    """The result of the first firing Deferred from a call to select."""
    def __init__(self, key, value=None, error=None):
        self.key = key
        self.value = value
        self.error = error

    def __call__(self, key):
        """Check if the selection key matches the given key.

        Args:
            key (str): The key to compare against the selected key.

        Returns:
            (bool): True if the given key matches what was selected, else False.
        """
        return key == self.key

    def result(self):
        """Get the result (or raise the error) from the selected Deferred."""
        if self.error is not None:
            raise self.error
        return self.value
