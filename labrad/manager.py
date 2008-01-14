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

from labrad import constants as C, util, types as T
from labrad.protocol import LabradProtocol, ILabradRequestProtocol
from labrad.decorators import setting
from labrad.util import mangle

from twisted.internet import reactor, protocol as tip
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import failure
from twisted.python.components import registerAdapter

import hashlib

from zope.interface import Interface

class ILabradServer(Interface):
    """The interface presented by a LabradServer to the connection

    Can this be the same as that presented by a server to a user?
    No!  The connection-visible interface contains methods that will be
    called by the framework.  The user-visible """

    def initServer(self):
        """Initialize the server."""

    def stopServer(self):
        """Shutdown the server."""

    def expireContext(self, context):
        """Expire a messaging context."""


class ILabradManager(Interface):
    def getServersList(self):
        pass

    def getServerInfo(self, serverID):
        pass

    def getSettingsList(self, serverID):
        pass

    def getSettingInfo(self, serverID, settingID):
        pass



class AsyncClientManager:
    def __init__(self, cxn):
        self.cxn = cxn

    def send(self, packet, *args, **kw):
        return self.cxn.request(C.MANAGER_ID, packet, *args, **kw)

    @inlineCallbacks
    def _getIDList(self, setting, data=None):
        resp = yield self.send((setting, data))
        names = [(mangle(name), name, ID) for ID, name in resp[0][1]]
        returnValue(names)

    def getServersList(self):
        return self._getIDList(C.SERVERS_LIST)

    @inlineCallbacks
    def getServerInfo(self, serverID):
        packet = [(C.SETTINGS_LIST, long(serverID)),
                  (C.HELP, long(serverID))]
        resp = yield self.send(packet)
        settings = _getIDList(resp, C.SETTINGS_LIST)
        try:
            descr, notes = _parseResp(resp, C.HELP)
        except:
            descr, notes = 'No server help text.', 'No notes.'
        returnValue((descr, notes, settings))

    def getSettingsList(self, serverID):
        return self._getIDList(C.SETTINGS_LIST, serverID)

    @inlineCallbacks
    def getSettingInfo(self, serverID, settingID):
        packet = [(C.HELP, (long(serverID), long(settingID)))]
        resp = yield self.send(packet)
        description, accepts, returns, notes = resp[0][1]
        returnValue((description, accepts, returns, notes))

registerAdapter(AsyncClientManager, ILabradRequestProtocol, ILabradManager)

def _getIDList(resp, ID):
    names = _parseResp(resp, ID)
    return [(mangle(name), name, ID) for ID, name in names]

def _getStringResp(resp, ID):
    return _parseResp(resp, ID)[0] or ''

def _parseResp(resp, desiredID):
    """Return a list of all data records for a given setting ID."""
    for ID, data in resp:
        if ID == desiredID:
            return data



