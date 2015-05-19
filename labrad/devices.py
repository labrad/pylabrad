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
labrad.devices

Superclass of generic device servers.
"""

from labrad import errors
from labrad.server import LabradServer, setting
from labrad.errors import Error
from labrad.support import MultiDict

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue

LOCK_TIMEOUT = 10

class DeviceLockedError(Error):
    """The device is locked."""
    # TODO should tell who holds lock and when it expires
    code = 4

class DeviceWrapper(object):
    """A wrapper for a device."""
    def __init__(self, guid, name):
        self.guid = guid # globally-unique identifier
        self.name = name
        self.locked = False
        self._lockContext = None
        self._unlockCall = None

    def lock(self, c, timeout_s=None):
        """Get or renew a lock on this device."""
        if not self.accessibleFrom(c):
            raise DeviceLockedError()
        self.locked = True
        self._lockContext = c
        timeout_s = timeout_s or LOCK_TIMEOUT
        if self._unlockCall is None:
            self._unlockCall = reactor.callLater(timeout_s, self.unlock)
        else:
            self._unlockCall.reset(timeout_s)

    def unlock(self, c=None):
        """Release the lock on this device."""
        c = c or self._lockContext
        if not self.accessibleFrom(c):
            raise DeviceLockedError()
        self.locked = False
        if self._unlockCall and self._unlockCall.active():
            self._unlockCall.cancel()
        self._unlockCall = None
        self._lockContext = None

    def lockedInContext(self, c):
        return self.locked and (self._lockContext == c)

    def accessibleFrom(self, c):
        return (not self.locked) or (self._lockContext == c)

    def connect(self, *args, **kw):
        """Connect to this device.

        This method will be called with the args and kw args returned
        by findDevices, when a new device is created.
        """

    def shutdown(self):
        """Called when we close the connection to this device."""

    def select(self, context):
        """Select this device in a context."""

    def deselect(self, context):
        """Deselect this device in a context."""

class DeviceServer(LabradServer):
    """A server for devices.

    Creates a DeviceWrapper for each device it finds, based on a
    user-provided function.  Provides standard settings for listing
    devices, selecting a device for the current context, and
    refreshing the list of devices.  Also, provides for device-locking
    with timeouts.
    """
    name = 'Generic Device Server'
    deviceWrapper = DeviceWrapper

    def initServer(self):
        self.devices = MultiDict() # aliases -> device
        self.device_guids = {} # name -> guid
        self._next_guid = 0
        self._refreshLock = defer.DeferredLock()
        return self.refreshDeviceList()

    def stopServer(self):
        if hasattr(self, 'devices'):
            ds = [defer.maybeDeferred(dev.shutdown)
                  for dev in self.devices.values()]
            return defer.DeferredList(ds, fireOnOneErrback=True)

    def findDevices(self):
        """Return a list of found devices.

        The result should be a list of (name, args, kw) tuples
        where args and kw are the arguments tuple and keyword dict
        that will be used to call the device's connect function.
        """
        return []

    def refreshDeviceList(self):
        """Refresh the list of available devices.

        Devices are assigned a unique identifying
        number that will persist between refreshes, so that
        clients that have selected devices in context will still
        be able to refer to them after the refresh.
        """
        return self._refreshLock.run(self._doRefresh)

    def chooseDeviceWrapper(self, *args, **kw):
        """
        Override in subclass to support multiple device wrapper classes

        args and kw come from findDevices (ie same as are passed into the
        device wrapper's connect method).
        """
        return self.deviceWrapper

    @inlineCallbacks
    def _doRefresh(self):
        """Do the actual refreshing."""
        self.log('refreshing device list...')
        all_found = yield self.findDevices()

        # If there are devices for which we don't have wrappers,
        # create them. If we have a wrapper for a
        # device that is no longer available, then that wrapper should
        # be marked somehow to indicate that it is no longer available.

        def fixFound(f):
            if isinstance(f, str):
                f = f, (), {}
            name = f[0]
            args = f[1] if len(f) > 1 else ()
            kw = f[2] if len(f) > 2 else {}
            return name, args, kw
        all_found = [fixFound(f) for f in all_found]

        additions = [(name, args, kw) for (name, args, kw) in all_found
                     if name not in self.devices]
        names_found = [name for (name, args, kw) in all_found]
        deletions = [name for name in self.device_guids
                     if name in self.devices and name not in names_found]
        self.log('all_found: %s' % all_found)
        self.log('additions: %s' % additions)
        self.log('deletions: %s' % deletions)

        # start additions
        for name, args, kw in additions:
            if name in self.device_guids:
                # we've seen this device before
                # so we'll reuse the old guid
                guid = self.device_guids[name]
            else:
                guid = self.device_guids[name] = self._next_guid
                self._next_guid += 1

            deviceWrapper = self.chooseDeviceWrapper(name, *args, **kw)
            dev = deviceWrapper(guid, name)
            yield dev.connect(*args, **kw)
            self.devices[guid, name] = dev

        # do deletions
        for name in deletions:
            # we delete the device, but not its guid, so that
            # if this device comes back, users who have
            # selected it by guid will reconnect seamlessly
            dev = self.devices[name]
            del self.devices[name]
            try:
                yield dev.shutdown()
            except Exception, e:
                self.log('Error while shutting down device "%s": %s' % (name, e))

    def serverConnected(self, ID, name):
        self.refreshDeviceList()

    def serverDisconnected(self, ID, name):
        self.refreshDeviceList()

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
            raise errors.NoSuchDeviceError(key)
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

    @setting(1, 'List Devices', returns=['*(ws)'])
    def list_devices(self, c):
        """List available devices."""
        IDs, names = self.deviceLists()
        return zip(IDs, names)

    @setting(2, 'Select Device',
                key=[': Select first device',
                     's: Select device by name',
                     'w: Select device by ID'],
                returns=['s: Name of the selected device'])
    def select_device(self, c, key=0):
        """Select a device for the current context."""
        dev = self.selectDevice(c, key=key)
        return dev.name

    @setting(3, 'Deselect Device', returns=[''])
    def deselect_device(self, c):
        """Select a device for the current context."""
        dev = self.deselectDevice(c)

    @setting(4, 'Refresh Devices', returns=['*(ws)'])
    def refresh_devices(self, c):
        """Refresh the list of available devices."""
        yield self.refreshDeviceList()
        returnValue(self.list_devices(c))

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

    @setting(1000002, 'Release Device', returns=[''])
    def release_device(self, c):
        """Release the lock on the currently-locked device."""
        dev = self.selectedDevice(c)
        dev.unlock(c.ID)

