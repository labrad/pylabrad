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
labrad module for python.
"""

from labrad import client, constants as C, manager, util
from labrad.wrappers import connectAsync, runAsync

__version__  = '0.92.6'
__revision__ = '$Revision$'
__date__     = '$Date$'

def connect(host=C.MANAGER_HOST, port=C.MANAGER_PORT, name=None, **kw):
    """Create a client connection to the labrad manager."""
    cxn = client.Connection(name)
    cxn.connect(host, port, **kw)
    return client.Client(cxn)

connection = connect
