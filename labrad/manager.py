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

import asyncio

from labrad import constants as C

class AsyncManager:
    """Adapt client to the ILabradManager interface."""

    ID = C.MANAGER_ID

    def __init__(self, cxn):
        self.cxn = cxn

    def _send(self, packet, *args, **kw):
        """Send a request to the manager."""
        return self.cxn.sendRequest(self.ID, packet, *args, **kw)

    @asyncio.coroutine
    def _get_id_list(self, setting, data, tag):
        resp = yield from self._send([(setting, data, tag)])
        names = self._reorder_id_list(resp[0][1])
        return names

    def _reorder_id_list(self, L):
        return [(name.decode('utf-8'), ID) for ID, name in L]

    def get_servers_list(self):
        """Get a list of connected servers."""
        return self._get_id_list(C.SERVERS_LIST, None, '_')

    @asyncio.coroutine
    def get_server_info(self, serverID):
        """Get information about a server."""
        packet = [(C.HELP, serverID, 'w'),
                  (C.SETTINGS_LIST, serverID, 'w')]
        resp = yield from self._send(packet)
        descr, notes = resp[0][1]
        settings = self._reorderIDList(resp[1][1])
        return (descr.decode('utf-8'), notes.decode('utf-8'), settings)

    @asyncio.coroutine
    def get_server_info_with_settings(self, serverID):
        """Get information about a server, including all of its settings."""
        packet = [(C.HELP, serverID, 'w'),
                  (C.SETTINGS_LIST, serverID, 'w')]
        resp = yield from self._send(packet)
        srv_descr, srv_notes = resp[0][1]
        settings = resp[1][1]
        packet = [(C.HELP, (serverID, ID), 'ww') for ID, name in settings]
        resp = yield from self._send(packet)
        setting_list = []
        for s, r in zip(settings, resp):
            ID, name = s
            descr, accepts, returns, notes = r[1]
            setting_list.append((
                name, ID, (
                    descr.decode('utf-8'),
                    [a.decode('utf-8') for a in accepts],
                    [r.decode('utf-8') for r in returns],
                    notes.decode('utf-8')
                )
            ))
        return (srv_descr.decode('utf-8'), srv_notes.decode('utf-8'), setting_list)

    def get_settings_list(self, serverID):
        """Get a list of settings for a server."""
        return self._get_id_list(C.SETTINGS_LIST, serverID, 'w')

    @asyncio.coroutine
    def get_setting_info(self, serverID, settingID):
        """Get information about a setting."""
        packet = [(C.HELP, (serverID, settingID), 'ww')]
        resp = yield from self._send(packet)
        description, accepts, returns, notes = resp[0][1]
        return (
            description.decode('utf-8'),
            [a.decode('utf-8') for a in accepts],
            [r.decode('utf-8') for r in returns],
            notes.decode('utf-8')
        )

    def subscribe_to_named_message(self, name, ID, enable=True):
        """Subscribe to or stop a named message."""
        packet = [(C.MESSAGE_SUBSCRIBE, (name, ID, enable), 'swb')]
        return self._send(packet)

