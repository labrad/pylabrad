import pytest


from labrad.decorators import setting
from labrad.server import LabradServer
from labrad import types


class DummyServer(LabradServer):
    @setting(100, param0='s: this is a string',
                  param1='b: this is a boolean')
    def dummy_setting(self, c, param0, param1):
        pass


def test_setting_types_with_comments():
    accepted_tags = DummyServer.dummy_setting.accepts
    accepted_types = [types.parseTypeTag(s) for s in accepted_tags]
    assert len(accepted_types) == 1
    assert accepted_types[0] == types.parseTypeTag('sb')


if __name__ == '__main__':
    pytest.main(['-v', __file__])
