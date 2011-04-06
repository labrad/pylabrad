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
        self.setDaemon(True)
    def run(self):
        reactor.run(installSignalHandlers=0)

_reactorThread = None

def startReactor():
    global _reactorThread
    if not _reactorThread or not _reactorThread.isAlive():
        _reactorThread = ReactorThread()
        _reactorThread.start()

def stopReactor(): 
    reactor.callFromThread(reactor.stop)

def blockingCallFromThread(func, *args, **kw):
    e = threading.Event()
    l = []
    def _got_result(result):
        l.append(result)
        e.set()
    def wrapped_func():
        d = defer.maybeDeferred(func, *args, **kw)
        d.addBoth(_got_result)
    reactor.callFromThread(wrapped_func)
    while True:
        e.wait(1)
        if e.isSet():
            break
    result = l[0]
    if isinstance(result, Failure):
        result.raiseException()
    else:
        return result

class Future(defer.Deferred):
    def __init__(self, func, *args, **kw):
        defer.Deferred.__init__(self)
        self.e = threading.Event()
        self.l = []
        def _got_result(result):
            self.l.append(result)
            self.e.set()
        def wrapped_func():
            d = defer.maybeDeferred(func, *args, **kw)
            d.addBoth(_got_result)
        reactor.callFromThread(wrapped_func)
        self.done = False
        self.result = None

    def addCallback(self, f, *args, **kw):
        if self.done:
            self.result = f(self.result, *args, **kw)
        else:
            self.callbacks.append((f, args, kw))
        return self
        
    def wait(self):
        if self.done:
            return self.result
        while True:
            self.e.wait(1)
            if self.e.isSet():
                break
            # TODO: check for KeyboardInterrupt here and cancel request
        self.done = True
        result = self.l[0]
        if isinstance(result, Failure):
            result.raiseException()
        else:
            for f, args, kw in self.callbacks:
                result = f(result, *args, **kw)
            self.result = result
            return result

    def __repr__(self):
        if self.done:
            return '<Future: result=%r>' % (self.result,)
        else:
            return '<Future: pending...>'
