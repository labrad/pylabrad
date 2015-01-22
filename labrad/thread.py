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

"""
labrad.thread

Methods to provide a blocking, threaded interface to the
asynchronous twisted backend.
"""

import threading

from twisted.internet import reactor, defer
from twisted.python import threadable
from twisted.python.failure import Failure

threadable.init(1)

class ReactorThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self, name='ReactorThread')
        self.daemon = True
    def run(self):
        reactor.run(installSignalHandlers=0)

_reactorThread = None

def startReactor():
    # check to see whether the reactor is already running
    # this ensures that when synchronous code is called from an asynchronous
    # program using deferToThread we don't try to restart the reactor
    if reactor.running:
        return
    global _reactorThread
    if not _reactorThread or not _reactorThread.isAlive():
        _reactorThread = ReactorThread()
        _reactorThread.start()

def stopReactor():
    reactor.callFromThread(reactor.stop)

