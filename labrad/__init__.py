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

from labrad import backend, client, constants

def connect(host=constants.MANAGER_HOST, port=None, name=None, **kw):
    """Create a client connection to the labrad manager."""
    cxn = backend.connect(host=host, port=port, name=name, **kw)
    return client.Client(cxn)

connection = connect
