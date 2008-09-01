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
from twisted.application import internet
from twisted.web import server

try:
    from twisted.internet import ssl
    from OpenSSL import SSL
    useSSL = True
except:
    useSSL = False

from labrad import constants as C
from labrad.controller import makeNodeControllerSite

class Options(usage.Options):
    optParameters = [['port', 'p', C.MANAGER_PORT, 'Manager port.'],
                     ['host', 'h', C.MANAGER_HOST, 'Manager location.']]

class ControllerPlugin(object):
    implements(IServiceMaker, IPlugin)
    tapname = 'labradcontrol'
    description = 'Control DMS Servers.'
    options = Options

    def makeService(self, options):
        """Construct a TCPServer from a DMS Controller page."""
        host = options['host']
        port = int(options['port'])

        site = makeNodeControllerSite(host, port)

        #if useSSL:
        #    contextFactory = ssl.DefaultOpenSSLContextFactory()
        #    adminService = internet.SSLServer(C.HTTP_PORT, site, contextFactory)
        #else:
        #    adminService = internet.TCPServer(C.HTTP_PORT, site)
        adminService = internet.TCPServer(C.HTTP_PORT, site)
        return adminService

controllerService = ControllerPlugin()
