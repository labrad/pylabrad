import pytest

import labrad
from labrad import util
from labrad.server import LabradServer, setting

class RefreshServer1(LabradServer):
    """First version of the refresh server."""

    name = 'Refresh Test Server'

    @setting(1, returns='s')
    def greet(self, c):
        return 'hello!'

    @setting(2, returns='_')
    def go_away(self, c):
        pass

class RefreshServer2(LabradServer):
    """Second version of the refresh server, with different settings."""
    name = 'Refresh Test Server'

    @setting(1, name='s', returns='s')
    def greet(self, c, name):
        return 'hello, {}!'.format(name)

    @setting(2, a='i', b='i', returns='i')
    def add(self, c, a, b):
        return a + b

def test_refresh():
    with labrad.connect() as cxn:

        assert not hasattr(cxn, 'refresh_test_server')

        with util.syncRunServer(RefreshServer1()):
            cxn.refresh()
            assert hasattr(cxn, 'refresh_test_server')
            rts = cxn.refresh_test_server

            assert hasattr(rts, 'greet')
            assert rts.greet.accepts == ['_']
            assert rts.greet.returns == ['s']

            assert hasattr(rts, 'go_away')
            assert rts.go_away.accepts == ['_']
            assert rts.go_away.returns == ['_']

            assert rts.greet() == 'hello!'

        cxn.refresh()
        assert not hasattr(cxn, 'refresh_test_server')

        with util.syncRunServer(RefreshServer2()):
            cxn.refresh()
            assert hasattr(cxn, 'refresh_test_server')

            # check the old rts we got earlier, as well as the cxn attribute
            for srv in [rts, cxn.refresh_test_server]:
                assert hasattr(srv, 'greet')
                assert srv.greet.accepts == ['s']
                assert srv.greet.returns == ['s']

                assert hasattr(srv, 'add')
                assert srv.add.accepts == ['(ii)']
                assert srv.add.returns == ['i']

                assert not hasattr(srv, 'go_away')

                assert srv.greet('tester') == 'hello, tester!'
                assert srv.add(100, 101) == 201

if __name__ == '__main__':
    pytest.main(['-v', __file__])
