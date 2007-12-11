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

# defaults for the labrad manager
MANAGER_ID = 1
MANAGER_PORT = int(os.environ.get('LABRADPORT', 7682))
MANAGER_HOST = os.environ.get('LABRADHOST', 'localhost')
PASSWORD = os.environ.get('LABRADPASSWORD', None)

# settings IDs on the LabRAD manager
SERVERS_LIST = 1
SETTINGS_LIST = 2
HELP = 10

NOTIFY_ON_CONNECT = 30L
NOTIFY_ON_DISCONNECT = 31L
NOTIFY_ON_CTX_EXP = 110L

# default timeout in ms
TIMEOUT = 30000

# node manager
HTTP_PORT = int(os.environ.get('LABRADHTTPPORT', 7667))
