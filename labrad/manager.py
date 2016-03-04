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


def _reorder_id_list(ids_and_names):
    """Reorder lists of (id, name) pairs to follow pylabrad (name, id) style."""
    return [(name, ID) for ID, name in ids_and_names]


def _id_or_name(value):
    """Flatten a value that can be a string name or unsigned int id."""
    return T.flatten(value, ['w', 's'])


class ManagerService:
    """Wraps a backend connection to provide a basic synchronous interface to the Manager."""
    def __init__(self, cxn):
        self.cxn = cxn

    def _send(self, packet, *args, **kw):
        """Send a request to the manager and wait for the result."""
        return self.cxn.sendRequest(C.MANAGER_ID, packet, *args, **kw).result()

    def _getIDList(self, setting, data=None):
        resp = self._send([(setting, data)])
        names = _reorder_id_list(resp[0][1])
        return names

    def getServersList(self):
        """Get list of connected servers."""
        return self._getIDList(C.SERVERS_LIST)

    def getServerInfo(self, server):
        """Get information about a server.

        Args:
            server (int or str): Name or ID of server.

        Returns:
            (str, str, list[(str, int)]): information about the server,
            consisting of description, notes, and a list of setting names and
            IDs.
        """
        packet = [(C.HELP, _id_or_name(server)),
                  (C.SETTINGS_LIST, _id_or_name(server))]
        resp = self._send(packet)
        descr, notes = resp[0][1]
        settings = _reorder_id_list(resp[1][1])
        return (descr, notes, settings)

    def getSettingsList(self, server):
        """Get list of settings for a server.

        Args:
            server (int or str): name or id of server.

        Returns:
            (list[(str, int)]): List of (name, id) pairs, one for each setting.
        """
        return self._getIDList(C.SETTINGS_LIST, _id_or_name(server))

    def getSettingInfo(self, server, setting):
        """Get information about a setting.

        Args:
            server (int or str): Name or ID of server.
            setting (int or str): Name or ID of setting.

        Returns:
            (str, list[str], list[str], str): information about the setting,
            consisting of description, list of accepted types, list of return
            types, and additional notes.
        """
        packet = [(C.HELP, (_id_or_name(server), _id_or_name(setting)))]
        resp = self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        return (description, accepts, returns, notes)

    def getSettingInfoByName(self, server, setting):
        """Get information about a setting using its name.

        Args:
            server (int or str): Name or ID of the server.
            setting (int or str): Name of ID of the setting.

        Returns:
            (str, list[str], list[str], str, int): information about the
            setting, consisting of description, list of accepted types, list of
            return types, additional notes, and the numeric ID.
        """
        packet = [(C.HELP, (_id_or_name(server), _id_or_name(setting))),
                  (C.LOOKUP, (_id_or_name(server), _id_or_name(setting)))]
        resp = self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        ID = resp[1][1][1]
        return (description, accepts, returns, notes, ID)


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
        names = _reorder_id_list(resp[0][1])
        returnValue(names)

    def getServersList(self):
        """Get a list of connected servers."""
        return self._getIDList(C.SERVERS_LIST)

    @inlineCallbacks
    def getServerInfo(self, server):
        """Get information about a server."""
        packet = [(C.HELP, _id_or_name(server)),
                  (C.SETTINGS_LIST, _id_or_name(server))]
        resp = yield self._send(packet)
        descr, notes = resp[0][1]
        settings = _reorder_id_list(resp[1][1])
        returnValue((descr, notes, settings))

    @inlineCallbacks
    def getServerInfoWithSettings(self, server):
        """Get information about a server, including all of its settings."""
        packet = [(C.HELP, _id_or_name(server)),
                  (C.SETTINGS_LIST, _id_or_name(server))]
        resp = yield self._send(packet)
        descr, notes = resp[0][1]
        settings = resp[1][1]
        packet = [(C.HELP, (_id_or_name(server), _id_or_name(ID)))
                  for ID, name in settings]
        resp = yield self._send(packet)
        settingList = []
        for s, r in zip(settings, resp):
            ID, name = s
            descr, accepts, returns, notes = r[1]
            settingList.append((name, ID, (descr, accepts, returns, notes)))
        returnValue((descr, notes, settingList))

    def getSettingsList(self, server):
        """Get a list of settings for a server."""
        return self._getIDList(C.SETTINGS_LIST, _id_or_name(server))

    @inlineCallbacks
    def getSettingInfo(self, server, setting):
        """Get information about a setting."""
        packet = [(C.HELP, (_id_or_name(server), _id_or_name(setting)))]
        resp = yield self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        returnValue((description, accepts, returns, notes))

    @inlineCallbacks
    def getSettingInfoByName(self, server, setting):
        """Get information about a setting using its name."""
        packet = [(C.HELP, (_id_or_name(server), _id_or_name(setting))),
                  (C.LOOKUP, (_id_or_name(server), _id_or_name(setting)))]
        resp = yield self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        ID = resp[1][1][1]
        returnValue((description, accepts, returns, notes, ID))

    @inlineCallbacks
    def subscribeToNamedMessage(self, name, ID, enable=True):
        """Subscribe to or stop a named message."""
        packet = [(C.MESSAGE_SUBSCRIBE, (name, _id_or_name(ID), enable))]
        returnValue((yield self._send(packet)))
