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

from zope.interface import implements, Interface, Attribute


class ILabradProtocol(Interface):
    """Basic LabRAD protocol to send messages and requests."""
    
    def sendMessage(target, records, context=(0, 0)):
        """Send a message to the specified target."""
        
    def sendRequest(target, records, context=(0, 0), timeout=None):
        """Send a request to the specified target server."""


class ILabradManager(Interface):
    """Interface to basic  LabRAD manager functions.
    
    Servers and Settings are given as lists of tuples of (mangled_name, name, ID).
    """
    
    def getServersList():
        """Get a list of connected servers."""

    def getServerInfo(server):
        """Get description, notes, and settings for specified server."""

    def getSettingsList(server):
        """Get list of settings for the specified server."""

    def getSettingInfo(server, setting):
        """Get info about a setting: description, accepted types, returned types, notes."""


class ILabradClient(Interface):
    """Interface for a generic LabRAD client."""
    def connect(host, port):
        """Connect to LabRAD."""
    
    
class ILabradServer(Interface):
    """Interface for implementing a LabRAD server."""
    
    client = Attribute("IClientAsync connection to LabRAD.")
    
    def initServer():
        """Initialize the server.
        
        This will be called after connecting to LabRAD.
        """

    def stopServer():
        """Shutdown the server.
        
        For an orderly shutdown, this will be called before disconnecting
        from LabRAD, so it should still be possible to make requests.
        """

    def newContext(ID):
        """Create a new context object for the given ID.
        
        By default, we create a dict-like object and set the ID
        attribute on it.  The object returned from this method
        will be passed to initContext for initialization.
        """
        
    def initContext(context):
        """Initialize a newly-created context object."""
        
    def expireContext(context):
        """Expire a messaging context."""
        
    def startRequest(context, source):
        """Start a request from source in the given context.
        
        By default, this sets the source attribute on the context,
        so that handlers called for this request can determine where
        the request originated.  Having set the ID and source attributes,
        the context object will now implement the IRequestContext interface
        when it is passed into the request handlers.
        """
    
    def serverConnected(ID, name):
        """Called when a new server connects to LabRAD."""
        
    def serverDisconnected(ID, name):
        """Called when a server disconnects from LabRAD."""


class IRequestContext(Interface):
    """Sent as the first argument to request handlers.
    
    A request context also usually implements a dict-like interface that
    servers can use to store persistent context information.
    """
    
    ID = Attribute("The context in which the message was sent, as a tuple of (high word, low word).")
    source = Attribute("The numeric ID of the request source.")


class IMessageContext(Interface):
    """Sent as the first argument to message handlers."""
    
    ID = Attribute("The context in which the message was sent, as a tuple of (high word, low word).")
    source = Attribute("The numeric ID of the message source.")
    target = Attribute("The numeric ID of the handler to which the message was sent.")
    
    
class IRequestHandler(Interface):
    """I can handle requests coming in over a LabRAD connection."""
    
    ID = Attribute("The numeric ID of this handler.")
    name = Attribute("The name of this handler.")
    accepts = Attribute("LabRAD types accepted by this handler.")
    returns = Attribute("LabRAD types returned by this handler.")
    description = Attribute("Text description of this handler.")
    notes = Attribute("Further notes about this handler.")
    
    def getRegistrationInfo():
        """Get information to register this handler with LabRAD."""
    
    def handleRequest(context, data):
        """Handle a remote request."""

class IMessageHandler(Interface):
    pass

class INamedMessageHandler(Interface):
    pass

class IClientAsync(Interface):
    """An asynchronous LabRAD client."""
    
    servers = Attribute("MultiDict that indexes available servers by name or ID.")
    
    def refresh():
        """Refresh the list of available servers and their settings."""
        
    def context():
        """Return a new context for messages and requests on this connection."""


class IRemoteServer(Interface):
    """A proxy class for a remote LabRAD server."""
    
    settings = Attribute("MultiDict that indexes available settings by name or ID.")
    
    def refresh():
        """Refresh the list of available settings and their info."""
        
    def context():
        """Return a new context for messages and requests to this server."""
        
    def packet():
        """Return a new packet for making a multi-part request to this server."""
        
    def sendMessage():
        """Send a message to this server."""
    

class IRemotePacket(Interface):
    """A packet to be sent to a remote server."""