from __future__ import absolute_import, print_function

import collections
import contextlib
import os
import subprocess
import sys
import time

import labrad
from labrad.servers import test_server


# Directory where test servers are located.
SERVERS_DIR = os.path.dirname(test_server.__file__)


# Infor about node that is yielded by the run_node context manager.
NodeInfo = collections.namedtuple('NodeInfo', [
    'node', 'node_name', 'node_server_name', 'node_reg'
])


@contextlib.contextmanager
def run_node(node_name, cxn, timeout=20):
    proc = subprocess.Popen([
        sys.executable,
        '-m', 'labrad.node',
        '--name={}'.format(node_name),
        '--host={}'.format(cxn.host),
        '--port={}'.format(cxn.port),
    ])
    node_server_name = 'node {}'.format(node_name)

    try:
        start = time.time()
        while True:
            cxn.refresh()
            if node_server_name in cxn.servers:
                break
            elapsed = time.time() - start
            if elapsed > timeout:
                raise Exception('node failed to start within {} seconds.'
                                .format(timeout))
            time.sleep(0.5)

        node_reg = cxn.registry()
        node_reg.cd(['', 'Nodes', node_name])
        node_reg.set('autostart', [])
        node_reg.set('directories', [SERVERS_DIR])
        node_reg.set('extensions', ['.ini', '.py'])

        node = cxn[node_server_name]
        node.refresh_servers()

        yield NodeInfo(node, node_name, node_server_name, node_reg)
    finally:
        proc.terminate()
        proc.wait()


def check_server(cxn, instance_name, connected):
    servers = [s for _, s in cxn.manager.servers()]
    cxn.refresh()
    assert (instance_name in servers) == connected
    assert (instance_name in cxn.servers) == connected


class TestNode(object):

    def test_node_autodetect(self):
        with labrad.connect() as cxn:
            with run_node('test', cxn) as n:
                servers = n.node.available_servers()
                assert 'Python Test Server' in servers
                assert 'Local Python Test Server' in servers
                n.node_reg.set('directories', [])
                n.node.refresh_servers()
                assert n.node.available_servers() == []

    def _test_start_server(self, node_name, name, instance_name, restart=False):
        with labrad.connect() as cxn:
            with run_node(node_name, cxn) as n:
                n.node.start(name)
                check_server(cxn, instance_name, connected=True)
                assert cxn[instance_name].echo('woot') == 'woot'
                if restart:
                    n.node.restart(instance_name)
                    check_server(cxn, instance_name, connected=True)
                    assert cxn[instance_name].echo('yay') == 'yay'
                n.node.stop(instance_name)
                check_server(cxn, instance_name, connected=False)

    def test_node_can_start_global_server(self):
        self._test_start_server(
            node_name='test',
            name='Python Test Server',
            instance_name='Python Test Server'
        )

    def test_node_can_restart_global_server(self):
        self._test_start_server(
            node_name='test',
            name='Python Test Server',
            instance_name='Python Test Server',
            restart=True
        )

    def test_node_can_start_local_server(self):
        self._test_start_server(
            node_name='test',
            name='Local Python Test Server',
            instance_name='test Local Python Test Server'
        )

    def test_node_can_restart_local_server(self):
        self._test_start_server(
            node_name='test',
            name='Local Python Test Server',
            instance_name='test Local Python Test Server',
            restart=True
        )

    def test_node_shuts_down_running_servers_when_stopped(self):
        with labrad.connect() as cxn:
            with run_node('test', cxn) as n:
                n.node.start('Python Test Server')
                n.node.start('Local Python Test Server')
                check_server(cxn, 'Python Test Server', connected=True)
                check_server(cxn, 'test Local Python Test Server', connected=True)
            check_server(cxn, 'Python Test Server', connected=False)
            check_server(cxn, 'test Local Python Test Server', connected=False)
