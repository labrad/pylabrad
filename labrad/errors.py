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
labrad.errors

Exception classes to provide convenient, informative error and debugging
information.
"""

from labrad.types import Error

## Network

class ConnectionTimeoutError(Exception):
    """Attempt to connect to labrad took too long."""

class LoginFailedError(Exception):
    """Failed to log in to LabRAD manager."""

## Servers

class DeviceNotSelectedError(Error):
    """No device has been selected in this context."""
    code = 1

class NoDevicesAvailableError(Error):
    """No devices are available."""
    code = 2

class NoSuchDeviceError(Error):
    """No such device exists."""
    code = 3

class RequestTimeoutError(Error):
    """The request timed out."""
    code = 4

class RequestResponseError(Error):
    code = 5
    def __init__(self, errors):
        messages = ['error in setting %d (code=%d)\n%s' % (ID, err.code, err.message)
                    for (ID, err) in errors]
        self.msg = '\n'.join(messages)
