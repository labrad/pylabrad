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

from labrad import util
from labrad.server import LabradServer, setting

from twisted.python import log
from twisted.internet.defer import inlineCallbacks

from datetime import datetime

DELAY_TIME = .25 # time to wait between measurements

class LoopServer(LabradServer):
    name = 'Test Looper'
    delayTime = DELAY_TIME
    testMode = True

    queries = [dict(server='manager',
                    setting='servers',
                    last=('', datetime.now()))]


    def initServer(self):
        self.alive = True
        self.readLoop().addErrback(log.err)

    def stopServer(self):
        self.alive = False

    @inlineCallbacks
    def readLoop(self):
        cxn = self.client
        while self.alive:
            yield cxn.refresh()
            for s in self.queries:
                server = s['server']
                setting = s['setting']
                try:
                    rslt = yield cxn[server][setting]()
                    s['last'] = str(rslt[0]), datetime.now()
                except Exception:
                    pass
            yield util.wakeupCall(self.delayTime)


    @setting(2, 'Queries', returns=['*s'])
    def list_queries(self, c):
        """A list of settings I query."""
        return [s['server'] + '.' + s['setting'] for s in self.queries]


    @setting(1, 'Get Readings', returns=['*(st)'])
    def get_readings(self, c):
        """Requests current readings."""
        return [s['last'] for s in self.queries]


    @setting(10, 'Delay Time', delay=['v[s]'], returns=['v[s]'])
    def delay_time(self, c, delay=None):
        if delay is not None:
            self.delayTime = delay
        return self.delayTime


__server__ = LoopServer()

if __name__ == '__main__':
    util.runServer(__server__)
