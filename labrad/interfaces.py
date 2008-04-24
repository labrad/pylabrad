# Copyright (C) 2008  Matthew Neeley
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

from zope.interface import Interface

class ILabradProtocol(Interface):
    """Basic LabRAD protocol to send messages and requests."""
    
    def sendMessage(self, target, records, context=(0, 0)):
        """Send a message to the specified target."""
        
    def sendRequest(self, target, records, context=(0, 0), timeout=None):
        """Send a request to the specified target server."""

class ILabradManager(Interface):
    """Interface to basic LabRAD manager functions.
    
    Servers and Settings are given as lists of tuples of (mangled_name, name, ID).
    """
    
    def getServersList(self):
        """Get a list of connected servers."""

    def getServerInfo(self, server):
        """Get description, notes, and settings for specified server."""

    def getSettingsList(self, server):
        """Get list of settings for the specified server."""

    def getSettingInfo(self, server, setting):
        """Get info about a setting: description, accepted types, returned types, notes."""

class ILabradClient(Interface):
    """Interface for a generic LabRAD client."""
    def connect(self, host, port):
        """Connect to LabRAD."""
    
    
class ILabradServer(Interface):
    """Interface for a generic LabRAD server."""
    
    def initServer(self):
        """Initialize the server."""

    def stopServer(self):
        """Shutdown the server."""

    def newContext(self, ID):
        """Create a new context object for the given ID."""
        
    def initContext(self, context):
        """Initialize a newly-created context object."""
        
    def expireContext(self, context):
        """Expire a messaging context."""

class IClientAsync(Interface):
    """An asynchronous LabRAD client."""
