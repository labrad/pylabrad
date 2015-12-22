# Copyright (C) 2007  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
labrad.constants

Important constants that show up throughout the code.
"""

import os
import labrad.crypto

DEFAULT_TLS = 'starttls' if labrad.crypto.TLS else 'off'

def check_tls_mode(tls_mode):
    """Check that provided tls mode is valid and convert to canonical form.

    Args:
        tls_mode (string): One of 'on', 'off', 'starttls', or 'starttls-force'.
            If 'on', we use TLS for the initial session establishment.
            If 'off', no TLS is used (for connecting to a legacy manager that
            does not support TLS). If 'starttls', the connection is initially
            unencrypted and will then be upgraded to a TLS connection after the
            initial handshake when connecting to a remote manager.
            If 'starttls-force', the client will behave like starttls mode but
            the connection will be upgraded to TLS even when connecting to the
            manager on localhost.

    Returns (string): tls mode in canonical (lowercase) form.

    Raises:
        ValueError: an invalid tls mode was specified
    """
    tls_mode = tls_mode.lower()
    if tls_mode not in ['on', 'off', 'starttls', 'starttls-force']:
        raise ValueError("tls mode must be one of 'on', 'off', 'starttls', or "
                         "'starttls-force'. got: '{}'".format(tls_mode))
    return tls_mode

# defaults for the labrad manager
MANAGER_ID = 1
MANAGER_PORT = int(os.environ.get('LABRADPORT', 7682))
MANAGER_TLS = check_tls_mode(os.environ.get('LABRAD_TLS', DEFAULT_TLS))
MANAGER_PORT_TLS = int(os.environ.get('LABRAD_TLS_PORT', 7643))
MANAGER_HOST = os.environ.get('LABRADHOST', 'localhost')
PASSWORD = os.environ.get('LABRADPASSWORD', None)

# settings IDs on the LabRAD manager
SERVERS_LIST = 1
SETTINGS_LIST = 2
LOOKUP = 3
HELP = 10
MESSAGE_SUBSCRIBE = 60

# default timeout in seconds
TIMEOUT = 30

# node controller
HTTP_PORT = int(os.environ.get('LABRADHTTPPORT', 7667))
