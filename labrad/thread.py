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
from concurrent import futures
import threading

class AsyncioExecutor(futures.Executor):
    """An executor that runs all submitted callables in an asyncio event loop.

    Manages a single thread which runs an asyncio event loop. Submitted
    tasks will be scheduled to run using the event loop's call_soon_threadsafe
    method. If the submitted callable returns a coroutine or Task, it will
    be run to completion inside the event loop and the final result returned.
    """

    _default = None

    @classmethod
    def get(cls):
        if cls._default is None:
            cls._default = AsyncioExecutor()
        return cls._default

    def __init__(self):
        super().__init__()
        loop_future = futures.Future()
        self._thread = threading.Thread(target=self._run, args=(loop_future,), daemon=True)
        self._thread.start()
        self._loop = loop_future.result()

    def _run(self, loop_future):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop_future.set_result(loop)
        try:
            loop.run_forever()
        except Exception:
            import traceback
            traceback.print_exc()
            raise
        loop.close()

    def submit(self, fn, *args, **kwargs):
        f = futures.Future()
        @asyncio.coroutine
        def task():
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                f.set_exception(Exception('asyncio event loop closed'))
            try:
                result = yield from fn(*args, **kwargs)
                f.set_result(result)
            except Exception as e:
                f.set_exception(e)
        self._loop.call_soon_threadsafe(asyncio.async, task())
        return f

    submit.__doc__ = futures.Executor.submit.__doc__

    def shutdown(self, wait=True):
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()

    shutdown.__doc__ = futures.Executor.shutdown.__doc__
