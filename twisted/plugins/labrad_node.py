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

from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker

from labrad import constants as C, util
from labrad.node import Node

class NodeOptions(usage.Options):
    optParameters = [['name', 'n', util.getNodeName(), 'Node name.'],
                     ['port', 'p', C.MANAGER_PORT, 'Manager port.'],
                     ['host', 'h', C.MANAGER_HOST, 'Manager location.']]

class NodePlugin(object):
    implements(IServiceMaker, IPlugin)
    tapname = 'labradnode'
    description = 'Node in a LabRAD network.'
    options = NodeOptions

    def makeService(self, options):
        """Construct a TCPServer from a LabRAD node."""
        name = options['name']
        host = options['host']
        port = int(options['port'])
        return Node(name, host, port)

nodeService = NodePlugin()
