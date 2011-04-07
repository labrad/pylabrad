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

from twisted.internet import reactor, defer
from twisted.internet.defer import \
    Deferred, DeferredQueue, inlineCallbacks, returnValue, _DefGen_Return
from twisted.python.failure import Failure

class PipeRunner(Deferred):
    """Run a single pipe generator.

    We make sure not to get ahead of the previous pipe,
    and also handle deferred results from any iteration
    of the generator.
    """
    
    def __init__(self, pipe, prev=None):
        Deferred.__init__(self)
        self.pipe = pipe
        self.prev = prev
        self.result = None
        self.waiting = False
        self.unblock = DeferredQueue()
        self.stage = 0
        if prev:
            # we will start when the previous pipe unblocks us
            self.waitForPrev()

    def run(self):
        """Run the pipe forward one step."""
        r = self.result
        try:
            if isinstance(r, Failure):
                r = self.pipe.throw(r.type, r.value, r.tb)
            else:
                r = self.pipe.send(r)
        except StopIteration:
            self.callback(None)
            self.unblockNext()
            return
        except _DefGen_Return, e:
            self.callback(e.value)
            self.unblockNext()
            return
        except:
            self.errback()
            self.unblockNext(Failure())
            return

        if isinstance(r, Deferred):
            # a deferred was yielded
            # continue after it finishes
            self.waiting = True
            print r.callbacks
            r.addBoth(self.gotResult)
            if self.waiting:
                # callback not yet executed
                self.waiting = False
                return
        else:
            self.result = r
        self.unblockNext()
        
        if self.prev:
            # wait for previous pipe before we continue
            self.waitForPrev()
        else:
            # we could go right ahead, but first we'll
            # yield execution so another pipe can go
            reactor.callLater(0, self.run)

    def gotResult(self, r):
        """Callback from a deferred pipe stage."""
        self.result = r
        if self.waiting:
            # we'll go right back to the run function
            self.waiting = False
        else:
            self.unblockNext()
            self.run()

    def waitForPrev(self):
        """Wait for the previous pipe to unblock us, then run one step."""
        d = self.prev.unblock.get()
        d.addCallback(lambda _: self.run())

    def unblockNext(self, err=None):
        """Called to unblock next pipe."""
        self.unblock.put(err)

DONE = object()

class Pipeline(Deferred):
    """Run a generator pipelined over a set of inputs."""
    def __init__(self, pipe, width=5):
        Deferred.__init__(self)
        self.pipe = pipe
        self.width = width
        self.waiting = None
        self.running = 0
        self.results = DeferredQueue()

    def run(self, inputs, *a, **kw):
        self._produce(inputs, *a, **kw)
        self._consume().chainDeferred(self)

    @inlineCallbacks
    def _produce(self, inputs, *a, **kw):
        prev = None
        for i, e in enumerate(inputs):
            if self.running >= self.width:
                # wait to add more pipes
                self.waiting = Deferred()
                yield self.waiting
            self.running += 1
            p = self.pipe(e, *a, **kw)
            pr = PipeRunner(p, prev=prev)
            pr.addBoth(self.results.put)
            if i == 0:
                pr.run()
            prev = pr
        pr.addBoth(lambda _: self.results.put(DONE))

    @inlineCallbacks
    def _consume(self):
        results = []
        while 1:
            r = yield self.results.get()
            if r == DONE:
                break
            self.running -= 1
            results.append(r)
            if self.waiting:
                d = self.waiting
                self.waiting = None
                d.callback(None)
        returnValue(results)

if __name__ == '__main__':
    from labrad.util import wakeupCall
    from random import randint

    LENGTH = 4
    N_PIPES = 10
    WIDTH = 5
    DELAYS = [0.05, 1, 0.05, 0.05]

    def printResult(r):
        print r
    
    def testPipe(ID, length=LENGTH):
        for k in range(length):
            @inlineCallbacks
            def stage(i):
                print 'starting:', (ID, k)
                yield wakeupCall(DELAYS[i % len(DELAYS)], (ID, i))
                print 'finished:', (ID, k)
            d = stage(k)
            d.addCallback(printResult)
            yield stage(k)
            #yield (ID, k)
        returnValue(ID)

    def printAndDie(result):
        print 'result:', result
        reactor.stop()
        print 'done.'

    def runTest():
        p = Pipeline(testPipe)
        p.width = WIDTH
        p.addBoth(printAndDie)
        p.run([chr(c) for c in range(65,65 + N_PIPES)])

    reactor.callWhenRunning(runTest)
    reactor.run()
