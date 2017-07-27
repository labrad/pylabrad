from __future__ import absolute_import, print_function

import collections
import contextlib
import os
import queue
import subprocess
import sys
import time

import labrad
from labrad.servers import test_server
from labrad.test import util


# Directory where test servers are located.
SERVERS_DIR = os.path.dirname(test_server.__file__)


# Infor about node that is yielded by the run_node context manager.
NodeInfo = collections.namedtuple('NodeInfo', [
    'node', 'node_name', 'node_server_name', 'node_reg'
])


@contextlib.contextmanager
def run_node(node_name, cxn, timeout=20, update_registry=True):
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

        node = cxn[node_server_name]
        node_reg = cxn.registry()

        if update_registry:
            node_reg.cd(['', 'Nodes', node_name])
            node_reg.set('autostart', [])
            node_reg.set('directories', [SERVERS_DIR])
            node_reg.set('extensions', ['.ini', '.py'])
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


@contextlib.contextmanager
def subscribe_to_node_messages(cxn):
    messages = [
        'node.server_starting',
        'node.server_started',
        'node.server_stopping',
        'node.server_stopped',
        'node.status',
    ]
    msg_map = {cxn.context()[1]: message_name for message_name in messages}

    message_queue = queue.Queue()
    def handler(message_ctx, msg):
        sender_id, msg_body = msg
        i = message_ctx.target
        if i in msg_map:
            message_name = msg_map[i]
            message_queue.put((message_name, msg_body))

    for i, message in msg_map.items():
        cxn.manager.subscribe_to_named_message(message, i, True)
    cxn._backend.cxn.addListener(handler)
    try:
        yield message_queue
    finally:
        cxn._backend.cxn.removeListener(handler)
        for i, message_name in msg_map.items():
            cxn.manager.subscribe_to_named_message(message, i, False)


def clear_queue(q):
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items


class TestNode(object):

    def test_node_autodetect(self):
        with labrad.connect() as cxn:
            with run_node('test', cxn) as n:
                servers = n.node.available_servers()
                assert 'Python Test Server' in servers
                assert 'Local Python Test Server' in servers

                with subscribe_to_node_messages(cxn) as mq:
                    n.node_reg.set('directories', [])
                    servers = self._check_status_message(mq.get(timeout=1))
                    assert servers == []
                assert n.node.available_servers() == []

                with subscribe_to_node_messages(cxn) as mq:
                    n.node_reg.set('directories', [SERVERS_DIR])
                    servers = self._check_status_message(mq.get(timeout=1))
                    assert 'Python Test Server' in servers
                    assert 'Local Python Test Server' in servers
                servers = n.node.available_servers()
                assert 'Python Test Server' in servers
                assert 'Local Python Test Server' in servers

    def test_node_status_on_startup(self):
        with labrad.connect() as cxn:
            with subscribe_to_node_messages(cxn) as mq:
                with run_node('test', cxn, update_registry=False) as n:
                    self._check_status_message(mq.get(timeout=1))

    def _check_status_message(self, message):
        message_name, contents = message
        assert message_name == 'node.status'
        contents = dict(contents)
        assert set(contents.keys()) == {'node', 'servers'}
        assert contents['node'] == 'node test'
        servers = [server[0] for server in contents['servers']]
        return servers

    def _test_start_server(self, node_name, name, instance_name, restart=False):
        expected_message = {
            'node': 'node {}'.format(node_name),
            'server': name,
            'instance': instance_name
        }

        def check_messages(message_queue, expected_names, timeout=1):
            """Check that we receive expected messages within the timeout."""
            remaining_names = list(expected_names)
            deadline = time.time() + timeout
            while remaining_names:
                try:
                    remaining = max(0, deadline - time.time())
                    message = message_queue.get(timeout=remaining)
                except queue.Empty:
                    raise Exception('messages not received before timeout: {}'
                                    .format(expected_names))
                message_name, message_params = message
                if message_name == remaining_names[0]:
                    remaining_names.remove(message_name)
                    assert dict(message_params) == expected_message

        with labrad.connect() as cxn:
            with run_node(node_name, cxn) as n:
                with subscribe_to_node_messages(cxn) as mq:
                    n.node.start(name)
                    check_messages(mq, [
                        'node.server_starting',
                        'node.server_started',
                    ])
                check_server(cxn, instance_name, connected=True)
                assert cxn[instance_name].echo('woot') == 'woot'
                if restart:
                    with subscribe_to_node_messages(cxn) as mq:
                        n.node.restart(instance_name)
                        check_messages(mq, [
                            'node.server_stopping',
                            'node.server_stopped',
                            'node.server_starting',
                            'node.server_started',
                        ])
                    check_server(cxn, instance_name, connected=True)
                    assert cxn[instance_name].echo('yay') == 'yay'
                with subscribe_to_node_messages(cxn) as mq:
                    n.node.stop(instance_name)
                    check_messages(mq, [
                        'node.server_stopping',
                        'node.server_stopped',
                    ])
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

    def test_node_detects_outdated_servers(self):
        config_template = """
            [info]
            name = Python Test Server
            version = {version}
            description = Basic python server.

            [startup]
            cmdline = %PYTHON% -m labrad.servers.test_server
            timeout = 20

            [shutdown]
            message = 987654321
            timeout = 5
        """
        with labrad.connect() as cxn:
            with run_node('test', cxn) as n:
                with util.temp_directory() as temp_dir:
                    # start running an existing server version
                    n.node.start('Python Test Server')
                    assert len(n.node.running_servers()) == 1
                    assert n.node.outdated_list() == None

                    # configure the node to see a newer version
                    with open(os.path.join(temp_dir, 'server2.ini'), 'w') as f:
                        f.write(config_template.format(version='2.0.0'))
                    n.node_reg.set('directories', [temp_dir, SERVERS_DIR])
                    time.sleep(0.5)  # TODO(#344): get rid of this pause
                    n.node.refresh_servers()

                    outdated_list = n.node.outdated_list()
                    assert outdated_list is not None
                    assert len(outdated_list) == 1
                    outdated = dict(outdated_list[0])
                    assert outdated['server'] == 'Python Test Server'
                    assert outdated['running_version'] == '1.0.0'
                    assert outdated['latest_version'] == '2.0.0'

                    # restart outdate server
                    outdated_restart = n.node.outdated_restart()
                    assert outdated_restart is not None
                    assert len(outdated_restart) == 1
                    restarted = dict(outdated_restart[0])
                    assert restarted['server'] == 'Python Test Server'
                    assert restarted['latest_version'] == '2.0.0'
                    assert restarted['status'] == 'restarted'
                    assert len(n.node.running_servers()) == 1
                    assert n.node.outdated_list() is None
