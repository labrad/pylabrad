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
Super Node

This labrad server finds and controls all available nodes.
"""

from labrad import types as T, util, errors, constants as C
from labrad.devices import DeviceWrapper, DeviceServer
from labrad.server import setting
from labrad.wrappers import connectAsync
from twisted.internet import defer
from twisted.internet.defer import inlineCallbacks, returnValue

class NodeWrapper(DeviceWrapper):
    """A wrapper for a node device."""

    def connect(self, node):
        """Connect to this node."""
        self.node = node # asynchronous wrapper for the node server

    def running_servers(self):
        return self.node.running_servers()

    def available_servers(self):
        return self.node.available_servers()

    def local_servers(self):
        return self.node.local_servers()

class SuperNode(DeviceServer):
    """A server mapping nodes to devices."""
    name = 'Super Node'
    deviceWrapper = NodeWrapper
    testMode = True

    def findDevices(self):
        cxn = self.client
        found = []
        for name in cxn.servers:
            if name.startswith('node_'):
                srv = cxn.servers[name]
                found.append((name, (srv,), {}))
        return found

    # server settings

    @setting(1001, returns=['*s'])
    def running_servers(self, c):
        """Get a list of running servers."""
        dev = self.selectedDevice(c)
        return dev.running_servers()

    @setting(1002, returns=['*s'])
    def available_servers(self, c):
        """Get a list of available servers."""
        dev = self.selectedDevice(c)
        return dev.available_servers()

    @setting(1003, returns=['*s'])
    def local_servers(self, c):
        """Get a list of local servers."""
        dev = self.selectedDevice(c)
        return dev.local_servers()

__server__ = SuperNode()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
