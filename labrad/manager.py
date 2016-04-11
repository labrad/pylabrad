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

from labrad import constants as C, types as T

class AsyncManager:
    """Provide an asynchronous interface to basic manager settings."""

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
        return self._getIDList(T.flatten(C.SERVERS_LIST, 'w'))

    @inlineCallbacks
    def getServerInfo(self, serverID):
        """Get information about a server."""
        packet = [(C.HELP, T.flatten(serverID, 'w')),
                  (C.SETTINGS_LIST, T.flatten(serverID, 'w'))]
        resp = yield self._send(packet)
        descr, notes = resp[0][1]
        settings = self._reorderIDList(resp[1][1])
        returnValue((descr, notes, settings))

    @inlineCallbacks
    def getServerInfoWithSettings(self, serverID):
        """Get information about a server, including all of its settings."""
        packet = [(C.HELP, T.flatten(serverID, 'w')),
                  (C.SETTINGS_LIST, T.flatten(serverID, 'w'))]
        resp = yield self._send(packet)
        descr, notes = resp[0][1]
        settings = resp[1][1]
        packet = [(C.HELP, T.flatten((serverID, ID), 'ww')) for ID, name in settings]
        resp = yield self._send(packet)
        settingList = []
        for s, r in zip(settings, resp):
            ID, name = s
            descr, accepts, returns, notes = r[1]
            settingList.append((name, ID, (descr, accepts, returns, notes)))
        returnValue((descr, notes, settingList))

    def getSettingsList(self, serverID):
        """Get a list of settings for a server."""
        return self._getIDList(C.SETTINGS_LIST, T.flatten(serverID, 'w'))

    @inlineCallbacks
    def getSettingInfo(self, serverID, settingID):
        """Get information about a setting."""
        packet = [(C.HELP, T.flatten((serverID, settingID), 'ww'))]
        resp = yield self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        returnValue((description, accepts, returns, notes))

    @inlineCallbacks
    def getSettingInfoByName(self, serverID, settingName):
        """Get information about a setting using its name."""
        packet = [(C.HELP, T.flatten((serverID, settingName), 'ws')),
                  (C.LOOKUP, T.flatten((serverID, settingName), 'ws'))]
        resp = yield self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        ID = resp[1][1][1]
        returnValue((description, accepts, returns, notes, ID))

    @inlineCallbacks
    def subscribeToNamedMessage(self, name, ID, enable=True):
        """Subscribe to or stop a named message."""
        packet = [(C.MESSAGE_SUBSCRIBE, T.flatten((name, ID, enable), 'swb'))]
        returnValue((yield self._send(packet)))
