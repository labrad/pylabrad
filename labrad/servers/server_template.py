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

from labrad.server import LabradServer

class ServerTemplate(LabradServer):
    """Template for a python LabRAD server.

    This doc string will appear as descriptive help text when
    this server connects to LabRAD.
    """

    # the server name will identify this server in LabRAD
    # note that this name should match that given in the
    # .ini file for this server, if you want to use this
    # server with the node.
    name = 'Python Server Template'

    # Server startup and shutdown
    #
    # these functions are called after we first connect to
    # LabRAD and before disconnecting.  Here you should perform
    # any global initialization or cleanup.
    def initServer(self):
        """Initialize Server.

        Called after registering settings and creating a client
        connection to labrad, but before we start serving requests.
        """

    def stopServer(self):
        """Stop the server.

        Called when the server is shutting down, but before we have
        closed any client connections.  Perform any cleanup operations here.
        """

    # Context handling
    #
    # these functions are called to initialize and expire
    # context objects for requests.  The object c is a
    # dict-like object that you can use to store and data you
    # would like to have associated with the context.  This same
    # context object will get passed in to request handlers as well.
    def initContext(self, c):
        """Initialize a new context object."""

    def expireContext(self, c):
        """Expire Context.

        Called when a client which created a context disconnects,
        or when the client explicitly requests the expiration.
        Any cleanup operations on the context should be done here.
        """

    # Manager notifications
    #
    # These functions will be called in response to notifications
    # from the manager about events happening in the LabRAD system.
    # They let you respond to the connection and disconnection
    # of other servers.
    def serverConnected(self, ID, name):
        """This function will be called when a new server connects to LabRAD."""

    def serverDisconnected(self, ID, name):
        """This function will be called when a server disconnects from LabRAD."""


# create an instance of our server class
__server__ = ServerTemplate()

# this is some boilerplate code to run the
# server when this module is executed
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
