# Copyright (C) 2013 Daniel Sank
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
### BEGIN NODE INFO
[info]
name = GPIB Mock Device Server
version = 1.0
description =

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

from labrad.server import setting
from labrad.gpib import GPIBManagedServer, GPIBDeviceWrapper
from twisted.internet.defer import inlineCallbacks, returnValue

class Mock0ADevice(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        """Notify that we are being made

        Note the important yield statement
        """
        print("Made a Mock0A device")
        yield

class Mock1BDevice(GPIBDeviceWrapper):
    @inlineCallbacks
    def initialize(self):
        """Notify that we are being made

        Note the important yield statement
        """
        print("Made a Mock1B device")
        yield

class GpibMockDeviceServer(GPIBManagedServer):
    """Provides basic CW control for Anritsu 68367C Microwave Generators"""
    name = 'GPIB Mock Device Server'
    deviceWrappers = {
                      'MOCK 0A': Mock0ADevice,
                      'MOCK 1B': Mock1BDevice
                      }

__server__ = GpibMockDeviceServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
