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

from labrad import types as T, constants as C, util, errors
from labrad.devices import DeviceWrapper, DeviceServer, DeviceLockedError
from labrad.server import LabradServer, setting
from labrad.support import MultiDict

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
        p = self._packet()
        p.address(self.addr)
        p.timeout(self._timeout)
        yield p.send()

        # do device-specific initialization
        yield self.initialize()

    def _packet(self):
        return self.gpib.packet(context=self._context)

    @inlineCallbacks
    def timeout(self, seconds):
        """Set the GPIB timeout for this device."""
        self._timeout = T.Value(seconds, 's')
        p = self._packet()
        p.timeout(self._timeout)
        yield p.send()

    @inlineCallbacks
    def query(self, query, bytes=None, timeout=None):
        """Query this GPIB device."""
        p = self._packet()
        if timeout is not None:
            p.timeout(timeout)
        p.query(query)
        if timeout is not None:
            p.timeout(self._timeout)
        resp = yield p.send()
        returnValue(resp.query)

    @inlineCallbacks
    def write(self, s, timeout=None):
        """Write a string to the device."""
        p = self._packet()
        if timeout is not None:
            p.timeout(timeout)
        p.write(s)
        if timeout is not None:
            p.timeout(self._timeout)
        resp = yield p.send()
        returnValue(resp.write)

    @inlineCallbacks
    def read(self, bytes=None, timeout=None):
        """Read a string from the device."""
        p = self._packet()
        if timeout is not None:
            p.timeout(timeout)
        p.read(bytes)
        if timeout is not None:
            p.timeout(self._timeout)
        resp = yield p.send()
        returnValue(resp.read)

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

    2013 October 22 - Daniel Sank
    I'm pretty sure this is obsolte and you should use the GPIBManagedServer
    """
    name = 'Generic GPIB Device Server'
    deviceName = 'Generic GPIB Device'
    deviceWrapper = GPIBDeviceWrapper

    def serverConnected(self, ID, name):
        """Refresh devices when a gpib server comes on line."""
        if 'gpib' in name.lower():
            self.refreshDeviceList()

    def serverDisconnected(self, ID, name):
        """Refresh devices when a gpib server goes off line."""
        if 'gpib' in name.lower():
            self.refreshDeviceList()

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
        for address, deviceName in zip(devices, ['<UNKNOWN>']*len(devices)):
            if deviceName == self.deviceName:
                name = _getDeviceName(srv, address)
                found.append((name, (srv, address), {}))
        returnValue(found)

    # server settings

    @setting(1001, 'GPIB Write', string='s', returns='*b')
    def gpib_write(self, c, string):
        """Write a string to the device over GPIB."""
        return self.selectedDevice(c).write(string)

    @setting(1002, 'GPIB Read', bytes='w', returns='s')
    def gpib_read(self, c, bytes=None):
        """Read a string from the device over GPIB."""
        return self.selectedDevice(c).read(bytes)

    @setting(1003, 'GPIB Query', query='s', returns='s')
    def gpib_query(self, c, query):
        """Write a string over GPIB and read the response."""
        return self.selectedDevice(c).query(query)

class ManagedDeviceServer(LabradServer):
    """A server for devices.

    Creates a DeviceWrapper for each device it finds, based on a
    user-provided function.  Provides standard settings for listing
    devices, selecting a device for the current context, and
    refreshing the list of devices.  Also, provides for device-locking
    with timeouts.

    Device names and associated wrappers can be specified in two ways
    1 (old way)
    Give a device name or list of device names:
    deviceName = "nameOfDevice" eg. "Acme XL123" or
    deviceName = ["nameOfDevice", "nameOfOtherDevice",...]
    and also give a single device wrapper.
    deviceWrapper=<a device Wrapper (sub)class>
    With this method the same device wrapper is used for all detected
    devices, regardless of eg. model. This works if all models use
    the same SCPI commands.
    2 (new better way)
    Give a dict mapping device names to wrappers
    deviceWrappers = {"deviceName":wrapperForThisDevice,...}
    This allows you to use the same server for eg. devices of the same
    general type but from different manufacturers or of different
    models.

    1. Old way example
    deviceName = "Acme Widget"
    deviceWrapper = AcmeWidgetWrapper
    2. New way example
    deviceWrappers={"Acme Widget": AcmeWidgetExample}

    Optionally specify a device specific identication function
    deviceIdentFunc = 'identify_device'
    """
    name = 'Generic Device Server'
    deviceManager = 'Device Manager'

    # Default device name and wrapper for backwards compatibility with servers
    # written before we supported multiple different device types, and which
    # do not explicitly set deviceWrapper and/or deviceName.
    deviceName = 'Generic Device'
    deviceWrapper = DeviceWrapper

    messageID = 21436587

    def __init__(self):
        #Backward compatibility for servers that don't use a
        #deviceWrappers dict
        if not hasattr(self, 'deviceWrappers'):
            names = self.deviceName
            if isinstance(names, str):
                names = [names]
            self.deviceWrappers = dict((name, self.deviceWrapper) for name in names)
        LabradServer.__init__(self)

    @inlineCallbacks
    def initServer(self):
        self.devices = MultiDict() # aliases -> device
        self.device_guids = {} # name -> guid
        self._next_guid = 0
        # register a message handler for connect/disconnect messages
        handler = lambda c, data: self.handleDeviceMessage(*data)
        self._cxn.addListener(handler, ID=self.messageID)
        if self.deviceManager in self.client.servers:
            yield self.connectToDeviceManager()

    @inlineCallbacks
    def stopServer(self):
        if hasattr(self, 'devices'):
            ds = [defer.maybeDeferred(dev.shutdown)
                  for dev in self.devices.values()]
            yield defer.DeferredList(ds, fireOnOneErrback=True)

    def makeDeviceName(self, device, server, address):
        return server + ' - ' + address

    @inlineCallbacks
    def handleDeviceMessage(self, device, server, address, isConnected=True):
        print 'Device message:', device, server, address, isConnected
        name = self.makeDeviceName(device, server, address)
        if isConnected: # add device
            if name in self.devices:
                return # we already have this device
            if name in self.device_guids:
                # we've seen this device before
                # so we'll reuse the old guid
                guid = self.device_guids[name]
            else:
                guid = self.device_guids[name] = self._next_guid
                self._next_guid += 1
            dev = self.deviceWrappers[device](guid, name)
            yield self.client.refresh()
            yield dev.connect(self.client[server], address)
            self.devices[guid, name] = dev

        else: # remove device
            yield self.removeDevice(name)

    @inlineCallbacks
    def removeDevice(self, name):
        # we delete the device, but not its guid, so that
        # if this device comes back, users who have
        # selected it by guid will reconnect seamlessly
        if name not in self.devices:
            return
        dev = self.devices[name]
        del self.devices[name]
        try:
            yield dev.shutdown()
        except Exception, e:
            self.log('Error while shutting down device "%s": %s' % (name, e))

    @inlineCallbacks
    def connectToDeviceManager(self):
        """

        """
        #yield self.client.refresh()
        manager = self.client[self.deviceManager]
        #If we have a device identification function register it with the device manager
        if hasattr(self, 'deviceIdentFunc'):
            yield manager.register_ident_function(self.deviceIdentFunc)
        #Register ourself as a server who cares about devices
        devs = yield manager.register_server(self.deviceWrappers.keys(), self.messageID)
        # the devs list is authoritative any devices we have
        # that are _not_ on this list should be removed
        names = [self.makeDeviceName(*dev[:3]) for dev in devs]
        additions = [self.handleDeviceMessage(*dev) for dev in devs]
        deletions = [self.removeDevice(name)
                     for name in self.device_guids.keys()
                     if name not in names]
        yield defer.DeferredList(additions + deletions)

    def serverConnected(self, ID, name):
        if name == self.deviceManager:
            self.connectToDeviceManager()

    def expireContext(self, c):
        """Release selected/locked device when context expires."""
        if 'device' in c:
            alias = c['device']
            try:
                dev = self.devices[alias]
                if dev.lockedInContext(c):
                    dev.unlock(c)
                dev.deselect(c)
            except KeyError:
                pass

    def deviceLists(self):
        """Get parallel lists of device names and IDs."""
        guids = sorted(self.devices.keys())
        names = [self.devices[g].name for g in guids]
        return guids, names

    def selectedDevice(self, context):
        """Get the selected device from the given context."""
        if not len(self.devices):
            raise errors.NoDevicesAvailableError()
        try:
            key = context['device']
        except KeyError:
            raise errors.DeviceNotSelectedError()
        try:
            dev = self.devices[key]
        except KeyError:
            raise errors.NoSuchDeviceError()
        if not dev.accessibleFrom(context.ID):
            raise DeviceLockedError()
        return dev

    def selectDevice(self, context, key=None):
        """Select a device in our current context."""
        if not len(self.devices):
            raise errors.NoDevicesAvailableError()
        if key is None:
            # use the first device
            key = sorted(self.devices.keys())[0]
        try:
            dev = self.devices[key]
        except KeyError:
            raise errors.NoSuchDeviceError()
        if not dev.accessibleFrom(context.ID):
            raise DeviceLockedError()

        if 'device' in context:
            if context['device'] != dev.guid:
                try:
                    oldDev = self.devices[context['device']]
                except KeyError:
                    pass
                else:
                    # we're trying to select a new device.
                    # make sure to unlock previously selected device
                    if oldDev.lockedInContext(context.ID):
                        oldDev.unlock(context.ID)
                    oldDev.deselect(context)
                context['device'] = dev.guid
                dev.select(context)
        else:
            context['device'] = dev.guid
            dev.select(context)
        return dev

    def deselectDevice(self, context):
        if 'device' in context:
            try:
                oldDev = self.devices[context['device']]
            except KeyError:
                pass
            else:
                # unlock and deselect device
                if oldDev.lockedInContext(context.ID):
                    oldDev.unlock(context.ID)
                oldDev.deselect(context)
            del context['device']

    def getDevice(self, context, key=None):
        if not len(self.devices):
            raise errors.NoDevicesAvailableError()
        if key is None:
            # use the first device
            key = sorted(self.devices.keys())[0]
        try:
            dev = self.devices[key]
        except KeyError:
            raise errors.NoSuchDeviceError()
        if not dev.accessibleFrom(context.ID):
            raise DeviceLockedError()
        return dev

    # server settings

    @setting(1, 'List Devices', returns='*(ws)')
    def list_devices(self, c):
        """Get a list of available devices.

        The list entries have a numerical ID and a string name.
        It is recommended to use the names wherever possible to
        identify devices, since this contains human-readable
        information about the device, however for speed numerical
        IDs may sometimes be desirable.  The ID number for a
        device is persistent, so it can be used even if the device
        disconnects and later reconnects under the same name.
        """
        IDs, names = self.deviceLists()
        return zip(IDs, names)

    @setting(2, 'Select Device',
                key=[': Select first device',
                     's: Select device by name',
                     'w: Select device by ID'],
                returns='s: Name of the selected device')
    def select_device(self, c, key=0):
        """Select a device for the current context."""
        dev = self.selectDevice(c, key=key)
        return dev.name

    @setting(3, 'Deselect Device', returns='')
    def deselect_device(self, c):
        """Deselect a device in the current context."""
        dev = self.deselectDevice(c)

    @setting(1000001, 'Lock Device',
                      timeout=[': Lock the selected device for default time',
                            'v[s]: Lock for specified time'],
                      returns=[''])
    def lock_device(self, c, timeout):
        """Lock a device to be accessible only in this context."""
        dev = self.selectedDevice(c)
        if timeout is not None:
            timeout = timeout['s']
        dev.lock(c.ID, timeout)

    @setting(1000002, 'Release Device', returns='')
    def release_device(self, c):
        """Release the lock on the currently-locked device."""
        dev = self.selectedDevice(c)
        dev.unlock(c.ID)

class GPIBManagedServer(ManagedDeviceServer):
    """A server for a GPIB device.

    Creates a GPIBDeviceWrapper for each device it finds that
    is appropriately named.  Provides standard settings for listing
    devices, selecting a device for the current context, and
    refreshing the list of devices.  Also, allows us to read from,
    write to, and query the selected GPIB device directly.
    """
    name = 'Generic GPIB Device Server'
    deviceManager = 'GPIB Device Manager'
    deviceName = 'Generic GPIB Device'
    deviceWrapper = GPIBDeviceWrapper
    # server settings

    @setting(1001, 'GPIB Write', string='s', timeout='v[s]', returns='')
    def gpib_write(self, c, string, timeout=None):
        """Write a string to the device over GPIB."""
        return self.selectedDevice(c).write(string, timeout)

    @setting(1002, 'GPIB Read', bytes='w', timeout='v[s]', returns='s')
    def gpib_read(self, c, bytes=None, timeout=None):
        """Read a string from the device over GPIB."""
        return self.selectedDevice(c).read(bytes, timeout)

    @setting(1003, 'GPIB Query', query='s', timeout='v[s]', returns='s')
    def gpib_query(self, c, query, timeout=None):
        """Write a string over GPIB and read the response."""
        return self.selectedDevice(c).query(query, timeout=timeout)

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
    return '%s - %s' % (server.name, deviceID)
