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

from labrad import types as T, constants as C
from labrad.devices import DeviceWrapper, DeviceServer
from labrad.server import setting

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
        self._timeout = T.Value(C.TIMEOUT, 's')
        
        # set the address and timeout in this context
        p = self.gpib.packet()
        p.address(self.addr)
        p.timeout(self._timeout)
        yield p.send(context=self._context)
        
        # do device-specific initialization
        yield self.initialize()

    def timeout(self, seconds):
        """Set the GPIB timeout for this device."""
        self._timeout = T.Value(seconds, 's')
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
    
    def serverConnected(self, ID, name):
        """Refresh devices when a gpib server comes on line."""
        if 'gpib' in name.lower():
            self.refreshDevices()
    
    def serverDisconnected(self, ID, name):
        """Refresh devices when a gpib server goes off line."""
        if 'gpib' in name.lower():
            self.refreshDevices()
    
    @inlineCallbacks
    def findDevices(self):
        """Find all available matching GPIB devices."""
        searches = [self._findDevicesForServer(srv)
                    for srv in _gpibServers(self.client)]
        found = []
        for search in searches:
            found += yield search
        returnValue(found)

    @inlineCallbacks
    def _findDevicesForServer(self, srv):
        """Find matching devices on a given server."""
        devices = yield srv.list_devices()
        found = []
        for address, deviceName in devices:
            if deviceName == self.deviceName:
                name = _getDeviceName(srv, address)
                found.append((name, (srv, address), {}))
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

def _gpibServers(cxn):
    """Get a list of available GPIB servers."""
    gpibs = []
    for name in cxn.servers:
        srv = cxn.servers[name]
        if 'gpib_bus' in name and 'list_devices' in srv.settings:
            gpibs.append(srv)
    return gpibs
        
def _getDeviceName(server, deviceID):
    """Create a name for a device on a particular server."""
    return '%s - GPIB ID %d' % (server.name, deviceID)
