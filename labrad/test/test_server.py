import Queue
import random

import pytest

import labrad
from labrad.server import LabradServer, setting
from labrad import util


def test_server_expire_context_method_is_called():
    """Ensure that server's expireContext method is called when client disconnects."""
    queue = Queue.Queue()

    class TestServer(LabradServer):
        name = "TestServer"

        def expireContext(self, c):
            queue.put(c.ID)

        @setting(100)
        def echo(self, c, data):
            return data

    with util.syncRunServer(TestServer()):
        with labrad.connect() as cxn:
            # create a random context owned by this connection
            request_context = (cxn.ID, random.randint(0, 0xFFFFFFFFL))
            cxn.testserver.echo('hello, world!', context=request_context)
        expired_context = queue.get(block=True, timeout=1)
        assert expired_context == request_context


def test_server_init_failure_is_propagated():

    class InitError(Exception):
        pass

    class DyingServer(LabradServer):
        name = "Dying Server"
        def initServer(self):
            raise InitError()

    with pytest.raises(InitError):
        with util.syncRunServer(DyingServer()):
            pass


if __name__ == '__main__':
    pytest.main(['-v', __file__])
