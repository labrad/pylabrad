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
labrad.gpib

Superclass of GPIB device servers.
"""

from labrad import types as T, util, errors, constants as C
from labrad.devices import DeviceWrapper, DeviceServer
from labrad.server import setting
from labrad.wrappers import connectAsync

from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue

class GPIBDeviceWrapper(DeviceWrapper):
    """A wrapper for a gpib device."""

    @inlineCallbacks
    def connect(self, gpib, addr):
        """Connect to this device.
        
        We set the address and timeout in the context reserved
        for talking to this device.  Then call initialize, which may
        be overridden in subclasses.
        """
        self.gpib = gpib # wrapper for the gpib server
        self.addr = addr
        self._context = gpib.context() # create a new context for this device
        self._timeout = T.Value(C.TIMEOUT, 'ms')
        
        p = self.gpib.packet()
        p.address(self.addr)
        p.timeout(self._timeout)
        yield p.send(context=self._context)
        yield self.initialize()

    def timeout(self, seconds):
        """Set the GPIB timeout for this device."""
        self._timeout = T.Value(seconds * 1000, 'ms')
        return self.gpib.timeout(self._timeout, context=self._context)

    def query(self, query, bytes=None):
        """Query this GPIB device."""
        p = self.gpib.packet()
        p.write(query).read(bytes)
        d = p.send(context=self._context)
        return d.addCallback(lambda r: r.read[0])

    def write(self, s):
        """Write a string to the device."""
        return self.gpib.write(s, context=self._context)

    def read(self, bytes=None):
        """Read a string from the device."""
        d = self.gpib.read(bytes, context=self._context)
        return d.addCallback(lambda r: r[0])

    def initialize(self):
        """Called when we first connect to the device.

        Override this in subclasses to perform device-specific
        initialization and to synchronize the wrapper state with
        the device state.
        """

class GPIBDeviceServer(DeviceServer):
    """A server for a GPIB device.
    
    Creates a GPIBDeviceWrapper for each device it finds that
    is appropriately named.  Provides standard settings for listing
    devices, selecting a device for the current context, and
    refreshing the list of devices.  Also, allows us to read from,
    write to, and query the selected GPIB device directly.
    """
    name = 'Generic GPIB Device Server'
    deviceName = 'Generic GPIB Device'
    deviceWrapper = GPIBDeviceWrapper

    @inlineCallbacks
    def initServer(self):
        yield DeviceServer.initServer(self)
        self.defaultCtxtData['device'] = 0

    @inlineCallbacks
    def findDevices(self):
        cxn = self.client
        found = []
        for name in cxn.servers:
            srv = cxn.servers[name]
            if 'gpib_bus' not in name or 'list_devices' not in srv.settings:
                continue
            devs = yield srv.list_devices()
            for addr, devName in devs:
                if devName != self.deviceName:
                    continue
                name = _deviceName(srv.name, addr)
                found.append((name, (srv, addr), {}))
        returnValue(found)

    # server settings

    @setting(1001, 'GPIB Write', string=['s'], returns=['*b'])
    def gpib_write(self, c, string):
        """Write a string to the device over GPIB."""
        return self.selectedDevice(c).write(string)

    @setting(1002, 'GPIB Read', bytes=['w'], returns=['s'])
    def gpib_read(self, c, bytes=None):
        """Read a string from the device over GPIB."""
        return self.selectedDevice(c).read(bytes)

    @setting(1003, 'GPIB Query', query=['s'], returns=['s'])
    def gpib_query(self, c, query):
        """Write a string over GPIB and read the response."""
        return self.selectedDevice(c).query(query)

def _deviceName(serverName, deviceID):
    return '%s - GPIB ID %d' % (serverName, deviceID)
