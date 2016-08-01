from __future__ import absolute_import

import getpass

from labrad import constants


class Password(object):
    def __init__(self, username='', password=''):
        self.username = username or ''
        self.password = password


# cache of username+password pairs, keyed by host name and port number
_password_cache = {}


def get_password(host=None, port=None, user=None, prompt=True):
    """Get a password from the environment, cache, or prompt.

    To add a password to the cache, use the cache_password function.

    Args:
        host (str or None): The manager host we want to connect to.
        port (int or None): The manager port we want to connect to.
        user (str or None): The user for which to get a password.
        prompt (bool): Whether to prompt the user to enter a password at the
            command line if none is found in the cache or environment vars.

    Returns:
        (Password or None): The password for the given host, port, and user. If
        we did not find a password in the cache or environment vars and prompt
        was False, will return None.
    """
    _init_password_cache()
    if host is None:
        host = constants.MANAGER_HOST
    if port is None:
        port = constants.MANAGER_PORT
    if user is None:
        user = constants.USERNAME or ''
    addr = (host, port)
    if addr in _password_cache and user in _password_cache[addr]:
        return _password_cache[addr][user]
    elif prompt:
        password = _prompt_for_password(host, port, user)
        return Password(user, password)
    else:
        return None


def get_username_and_password(host, port, prompt=True):
    """Get a username and password from the environment, cache, or prompt.

    To add a password to the cache, use the cache_password function.

    Args:
        host (str or None): The manager host we want to connect to.
        port (int or None): The manager port we want to connect to.
        prompt (bool): Whether to prompt the user to enter a password at the
            command line if none is found in the cache or environment vars.

    Returns:
        (Password or None): Credential object containing username and password
        for the given host, port.
    """
    _init_password_cache()
    if host is None:
        host = constants.MANAGER_HOST
    if port is None:
        port = constants.MANAGER_PORT
    addr = (host, port)
    if addr in _password_cache and _password_cache[addr]:
        passwords = _password_cache[addr]
        for user in passwords.keys():
            if user:
                break
        return passwords[user]
    elif prompt:
        user = raw_input('Enter username, or blank for the global user '
                         '({}:{}): '.format(host, port))
        password = _prompt_for_password(host, port, user)
        return Password(user, password)
    else:
        return None


def cache_password(host, port, credential):
    """Add a password to the cache, for the given host and port.

    Cached passwords will be used for subsequent labrad connections to the same
    host and port. See the get_password function.

    Args:
        host (str): The manager host for this password.
        port (int): The manager port for this password.
        credential (Password): The username and password to cache.
    """
    passwords = _password_cache.setdefault((host, port), {})
    passwords[credential.username] = credential


def _prompt_for_password(host, port, user):
    """Prompt user to enter a password for the given host, port, and user."""
    if user:
        msg = 'Enter LabRAD password for {} ({}:{}): '.format(user, host, port)
    else:
        msg = 'Enter LabRAD password ({}:{}): '.format(host, port)
    return getpass.getpass(msg)


def _init_password_cache():
    """Create cache entries for the environment password if needed."""
    if not _password_cache and constants.PASSWORD is not None:
        credential = Password(constants.USERNAME, constants.PASSWORD)
        cache_password(constants.MANAGER_HOST,
                       constants.MANAGER_PORT,
                       credential)
        cache_password(constants.MANAGER_HOST,
                       constants.MANAGER_PORT_TLS,
                       credential)
