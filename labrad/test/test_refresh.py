import time

import pytest

import labrad
from labrad import types as T, util
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

class RefreshServer3(LabradServer):
    """Third version of the refresh server, with original settings but differing IDs."""
    name = 'Refresh Test Server'

    @setting(10, returns='s')
    def greet(self, c):
        return 'hello!'

    @setting(20, returns='_')
    def go_away(self, c):
        pass

def test_refresh():
    with labrad.connect() as cxn:

        assert not hasattr(cxn, 'refresh_test_server')

        with util.syncRunServer(RefreshServer1()):
            cxn.refresh()
            assert hasattr(cxn, 'refresh_test_server')
            rts = cxn.refresh_test_server

            def type_list(strs):
                return [T.parseTypeTag(s) for s in strs]

            def same_types(a, b):
                return type_list(a) == type_list(b)

            assert hasattr(rts, 'greet')
            assert same_types(rts.greet.accepts, ['_'])
            assert same_types(rts.greet.returns, ['s'])

            assert hasattr(rts, 'go_away')
            assert same_types(rts.go_away.accepts, ['_'])
            assert same_types(rts.go_away.returns, ['_'])

            assert rts.greet() == 'hello!'

        # pause before refreshing after server disconnect
        time.sleep(1)

        cxn.refresh()
        assert not hasattr(cxn, 'refresh_test_server')

        with util.syncRunServer(RefreshServer2()):
            cxn.refresh()
            assert hasattr(cxn, 'refresh_test_server')

            # check the old rts we got earlier, as well as the cxn attribute
            for srv in [rts, cxn.refresh_test_server]:
                assert hasattr(srv, 'greet')
                assert same_types(srv.greet.accepts, ['s'])
                assert same_types(srv.greet.returns, ['s'])

                assert hasattr(srv, 'add')
                assert same_types(srv.add.accepts, ['(ii)'])
                assert same_types(srv.add.returns, ['i'])

                assert not hasattr(srv, 'go_away')

                assert srv.greet('tester') == 'hello, tester!'
                assert srv.add(100, 101) == 201

        # pause before refreshing after server disconnect
        time.sleep(1)

        cxn.refresh()
        assert not hasattr(cxn, 'refresh_test_server')

        with util.syncRunServer(RefreshServer3()):
            cxn.refresh()
            assert hasattr(cxn, 'refresh_test_server')

            # check the old rts we got earlier, as well as the cxn attribute
            for srv in [rts, cxn.refresh_test_server]:
                assert hasattr(rts, 'greet')
                assert same_types(rts.greet.accepts, ['_'])
                assert same_types(rts.greet.returns, ['s'])

                assert hasattr(rts, 'go_away')
                assert same_types(rts.go_away.accepts, ['_'])
                assert same_types(rts.go_away.returns, ['_'])

                assert rts.greet() == 'hello!'

if __name__ == '__main__':
    pytest.main(['-v', __file__])
