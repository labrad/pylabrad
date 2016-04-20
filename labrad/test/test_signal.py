import Queue

import pytest

import labrad
from labrad.server import LabradServer, setting, Signal
import labrad.util


class SignalTestServer(LabradServer):
    name = "Signal Test Server"

    class_signal = Signal(100, 'class_signal', '?')

    def __init__(self):
        super(SignalTestServer, self).__init__()
        self.instance_signal = Signal(200, 'instance_signal', '?')

    @setting(101)
    def fire_class_signal(self, c, data):
        self.class_signal(data)

    @setting(201)
    def fire_instance_signal(self, c, data):
        self.instance_signal(data)


def _test_signals(signal_setting, fire_setting):
    with labrad.util.syncRunServer(SignalTestServer()):
        with labrad.connect() as cxn:
            server = cxn.signal_test_server
            msg_id = 12345

            # add a listener to enqueue all messages
            queue = Queue.Queue()
            def handler(message_ctx, msg):
                queue.put((message_ctx, msg))
            cxn._backend.cxn.addListener(handler, ID=msg_id)

            # we don't get messages before signing up
            server[fire_setting]('not listening')
            with pytest.raises(Queue.Empty):
                queue.get(block=True, timeout=1)

            server[signal_setting](msg_id)
            server[fire_setting]('listening')
            msg_ctx, msg = queue.get(block=True, timeout=1)
            assert msg_ctx.source == server.ID
            assert msg == 'listening'

            server[signal_setting]()
            server[fire_setting]('not listening')
            with pytest.raises(Queue.Empty):
                queue.get(block=True, timeout=1)


def test_signal_can_be_defined_on_server_class():
    _test_signals('class_signal', 'fire_class_signal')


def test_signal_can_be_defined_on_server_instance():
    _test_signals('instance_signal', 'fire_instance_signal')


if __name__ == '__main__':
    pytest.main(['-v', __file__])
