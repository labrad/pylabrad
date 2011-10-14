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

from twisted.internet.defer import inlineCallbacks, returnValue

from labrad import constants as C

class AsyncManager:
    """Adapt client to the ILabradManager interface."""
    
    ID = C.MANAGER_ID
    
    def __init__(self, cxn):
        self.cxn = cxn

    def _send(self, packet, *args, **kw):
        """Send a request to the manager."""
        return self.cxn.sendRequest(self.ID, packet, *args, **kw)

    @inlineCallbacks
    def _getIDList(self, setting, data=None):
        resp = yield self._send([(setting, data)])
        names = self._reorderIDList(resp[0][1])
        returnValue(names)

    def _reorderIDList(self, L):
        return [(name, ID) for ID, name in L]
        
    def getServersList(self):
        """Get a list of connected servers."""
        return self._getIDList(C.SERVERS_LIST)

    @inlineCallbacks
    def getServerInfo(self, serverID):
        """Get information about a server."""
        packet = [(C.HELP, long(serverID)),
                  (C.SETTINGS_LIST, long(serverID))]
        resp = yield self._send(packet)
        descr, notes = resp[0][1]
        settings = self._reorderIDList(resp[1][1])
        returnValue((descr, notes, settings))

    @inlineCallbacks
    def getServerInfoWithSettings(self, serverID):
        """Get information about a server, including all of its settings."""
        packet = [(C.HELP, long(serverID)),
                  (C.SETTINGS_LIST, long(serverID))]
        resp = yield self._send(packet)
        descr, notes = resp[0][1]
        settings = resp[1][1]
        packet = [(C.HELP, (long(serverID), long(ID))) for ID, name in settings]
        resp = yield self._send(packet)
        settingList = []
        for s, r in zip(settings, resp):
            ID, name = s
            descr, accepts, returns, notes = r[1]
            settingList.append((name, ID, (descr, accepts, returns, notes)))
        returnValue((descr, notes, settingList))

    def getSettingsList(self, serverID):
        """Get a list of settings for a server."""
        return self._getIDList(C.SETTINGS_LIST, serverID)

    @inlineCallbacks
    def getSettingInfo(self, serverID, settingID):
        """Get information about a setting."""
        packet = [(C.HELP, (long(serverID), long(settingID)))]
        resp = yield self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        returnValue((description, accepts, returns, notes))
        
    @inlineCallbacks
    def subscribeToNamedMessage(self, name, ID, enable=True):
        """Subscribe to or stop a named message."""
        packet = [(C.MESSAGE_SUBSCRIBE, (name, long(ID), enable))]
        returnValue((yield self._send(packet)))

