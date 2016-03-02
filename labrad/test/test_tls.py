import collections
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

import pytest

import labrad
from labrad import crypto


@contextlib.contextmanager
def temp_tls_dirs():
    """Context manager to create temporary dirs for labrad TLS certs and keys.

    Also overrides the path labrad.crypto.CERTS_PATH where we look for trusted
    certs to correspond to the temporary directory. If we then also point the
    manager to this directory to store its generated self-signed certificates,
    then we will automatically trust those certificates.

    Yields (string, string):
        A tuple of paths for the TLS certs and keys, respectively.
    """
    user_dir = os.path.expanduser('~')
    cert_path = tempfile.mkdtemp(prefix='.labrad-test-certs', dir=user_dir)
    key_path = tempfile.mkdtemp(prefix='.labrad-test-keys', dir=user_dir)
    old_cert_path = crypto.CERTS_PATH
    crypto.CERTS_PATH = cert_path
    try:
        yield cert_path, key_path
    finally:
        crypto.CERTS_PATH = old_cert_path
        shutil.rmtree(cert_path)
        shutil.rmtree(key_path)


# Manager Info class returned by the run_manager cont
ManagerInfo = collections.namedtuple('ManagerInfo', ['port', 'tls_port', 'password'])


@contextlib.contextmanager
def run_manager(tls_required, port=7778, tls_port=7779, startup_timeout=20):
    """Context manager to run the labrad manager in a subprocess.

    Will attempt to connect to the manager and fail if we cannot do so within
    the specified timeout. This ensures that the manager is actually running
    and listening for connections before we yield to execute the body of the
    with statement.

    Args:
        tls_required (boolean): Whether the manager should require TLS.
        port (int): The port on which to listen for upgradeable connections
            that start unencrypted and then use STARTTLS to secure the
            connection.
        tls_port (int): The port on which to listen for TLS connections that
            are encrpyted from the start.
        startup_timeout (float): Maximum number of seconds to allow for the
            manager to start before we fail.

    Yields (ManagerInfo):
        Info about the running manager.
    """
    with temp_tls_dirs() as (cert_path, key_path):
        password = 'DummyPassword'
        manager = subprocess.Popen([
                'labrad',
                '--password={}'.format(password),
                '--port={}'.format(port),
                '--tls-port={}'.format(tls_port),
                '--tls-required={}'.format(tls_required),
                '--tls-required-localhost={}'.format(tls_required),
                '--tls-cert-path={}'.format(cert_path),
                '--tls-key-path={}'.format(key_path)])
        try:
            start = time.time()
            while True:
                try:
                    labrad.connect(port=tls_port, tls_mode='on',
                                   password=password)
                except Exception, e:
                    last_error = e
                else:
                    break
                elapsed = time.time() - start
                if elapsed > startup_timeout:
                    raise Exception('labrad failed to start within {} seconds. '
                                    'last_error={}'
                                    .format(startup_timeout, last_error))
                time.sleep(0.5)
            yield ManagerInfo(port, tls_port, password)
        finally:
            manager.kill()


# Test that we can establish encrypted TLS connections to the manager

def test_connect_with_starttls():
    with run_manager(tls_required=True) as m:
        with labrad.connect(port=m.port, tls_mode='starttls-force',
                            password=m.password) as cxn:
            pass

def test_connect_with_optional_starttls():
    with run_manager(tls_required=False) as m:
        with labrad.connect(port=m.port, tls_mode='off',
                            password=m.password) as cxn:
            pass

def test_connect_with_tls():
    with run_manager(tls_required=True) as m:
        with labrad.connect(port=m.tls_port, tls_mode='on',
                            password=m.password) as cxn:
            pass


# Test that connecting to the manager fails if the client fails to
# use TLS when the manager expects it.

def test_expect_starttls_use_off():
    with run_manager(tls_required=True) as m:
        with pytest.raises(Exception):
            with labrad.connect(port=m.port, tls_mode='off',
                                password=m.password) as cxn:
                pass

def test_expect_tls_use_off():
    with run_manager(tls_required=True) as m:
        with pytest.raises(Exception):
            with labrad.connect(port=m.tls_port, tls_mode='off',
                                password=m.password) as cxn:
                pass

def test_expect_tls_use_starttls():
    with run_manager(tls_required=True) as m:
        with pytest.raises(Exception):
            with labrad.connect(port=m.tls_port, tls_mode='off',
                                password=m.password) as cxn:
                pass


if __name__ == '__main__':
    pytest.main(['-v', __file__])
