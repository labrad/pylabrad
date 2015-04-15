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

Run an asyncio event loop in a thread. This one event loop will
be shared by all synchronous labrad connections.
"""

import asyncio
import threading

class AsyncioThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self, name='AsyncioThread')
        self.daemon = True
        self.loop = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.close()

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.join()

_asyncio_thread = None

def start_asyncio():
    # check to see whether the reactor is already running
    # this ensures that when synchronous code is called from an asynchronous
    # program using deferToThread we don't try to restart the reactor
    global _asyncio_thread
    if _asyncio_thread is None:
        _asyncio_thread = AsyncioThread()
        _asyncio_thread.start()

def stop_asyncio():
    global _asyncio_thread
    if _asyncio_thread is not None:
        _asyncio_thread.close()
        _asyncio_thread = None

