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
from labrad.thread import Future, startReactor, stopReactor
from twisted.internet.defer import returnValue, _DefGen_Return

def waitFor(*ds):
    for d in ds:
        d.wait()

class FutureList(Future):
    def __init__(self, ds):
        self.ds = ds
    def wait(self):
        return [(d.wait() if isinstance(d, Future) else d) for d in self.ds]


class PipelineBase:
    """Allows one to run a generator pipelined over an input set."""

    def __init__(self, pipe):
        self.pipe = pipe

    def run(self, inputs, *a, **kw):
        """Run the given inputs through the pipeline."""

        self.pipes = []
        self.results = []

        # create the pipes
        for elem in inputs:
            p = self.pipe(elem, *a, **kw)
            self.pipes.append([p, None])
            self._runAllOnce()

        # run until all pipes are done
        while len(self.pipes):
            self._runAllOnce()

        return self.results

    def _runAllOnce(self):
        """Run each pipe forward one step."""

        done = []

        for i, (pipe, prev) in enumerate(self.pipes):
            try:
                r = pipe.send(prev)
            except StopIteration:
                done.insert(0, i)
                continue
            except _DefGen_Return, e:
                done.insert(0, i)
                self.results.append(e.value)
                continue

            if isinstance(r, tuple):
                if isinstance(r[0], Priority):
                    r = r[1:]
                r = FutureList(r)

            self.pipes[i][1] = r

        # remove completed pipes
        for i in done:
            del self.pipes[i]

        # wait for all pipes to finish
        for p in self.pipes:
            if isinstance(p[1], Future):
                p[1] = p[1].wait()


class Priority:
    """A simple class to represent different execution priorities.

    This needs to be a class so that we can unambiguously check
    whether a priority instruction has been yielded by a pipe.
    Lower levels are prioritized to execute first.
    """

    def __init__(self, level):
        self.level = level

    def __repr__(self):
        return 'Priority(%d)' % self.level

# some priority constants
FIRST = Priority(0)
EARLIER = Priority(25)
DEFAULT = Priority(50)
LATER = Priority(75)
LAST = Priority(100)


class PriorityList:
    """Keeps track of priorities and execution order for steps.

    This functions like a dictionary for registering priorities:

        priorityList[step] = priority

    and can be iterated over to give the steps in order:

        for step in priorityList:
            ...do something...

    A step priority can be set multiple times and the order will
    be recalculated.
    """

    def __init__(self):
        self.order = []
        self.steps = {}

    def __setitem__(self, k, v):
        if isinstance(v, Priority):
            v = v.level
        for p in self.steps:
            l = self.steps[p]
            if k in l:
                i = l.index(k)
                del l[i]
        if v not in self.steps:
            self.steps[v] = []
        self.steps[v].append(k)
        self._reorder()

    def _reorder(self):
        priorities = self.steps.keys()
        priorities.sort()
        self.order = []
        for p in priorities:
            self.order.extend(self.steps[p])
        #print 'priority order:', self.order

    def __iter__(self):
        return iter(self.order)

    def __len__(self):
        return len(self.order)

    def reverse(self):
        p = self.order[:]
        p.reverse()
        return p

class Pipeline(PipelineBase):
    """Run a generator over a set of inputs with prioritized stages.

    The priority hints are yielded from the pipe as the leading
    member of a tuple.  This is only kept track of during the
    run of the first generator.
    """
    def run(self, inputs, *a, **kw):
        """Run the given inputs through the pipeline."""

        self.pipes = []
        self.results = []
        self.first = None

        self.priority = PriorityList()

        # create the pipes
        for elem in inputs:
            p = self.pipe(elem, *a, **kw)
            if len(self.pipes) and self.pipes[0][0] is None:
                del self.pipes[0]
            self.pipes.insert(0, [p, None])
            self.first = self.first or p
            self._runAllOnce()

        # run until all pipes are done
        while any([p[0] is not None for p in self.pipes]):
            self._runAllOnce()

        return self.results

    def _runAllOnce(self):
        """Run each pipe forward one step, in priority order."""

        done = []

        # set default priority for all steps we haven't seen yet
        for step in range(len(self.priority), len(self.pipes)):
            self.priority[step] = DEFAULT

        for i in self.priority:
            p, prev = self.pipes[i]
            if p is None:
                continue
            try:
                r = p.send(prev)
            except StopIteration:
                # we can't remove the pipes immediately, since
                # that would throw of the indexing.  Instead,
                # we mark them for later deletion
                done.insert(0, i)
                continue
            except _DefGen_Return, e:
                done.insert(0, i)
                self.results.append(e.value)
                continue

            # save any hints about priority
            if isinstance(r, tuple) and isinstance(r[0], Priority):
                if p == self.first:
                    self.priority[i] = r[0]
                r = r[1:]

            if isinstance(r, tuple):
                r = FutureList(r)

            # store the result to send back in next time around
            self.pipes[i][1] = r

        # remove completed pipes
        for i in done:
            p = self.pipes[i]
            del self.pipes[i]
            if p != self.first:
                self.pipes.insert(0, [None, None])

        # wait for all pipes to finish
        for i in self.priority.reverse():
            p = self.pipes[i]
            if isinstance(p[1], Future):
                p[1] = p[1].wait()


def run(pipe, inputs, *a, **kw):
    """Run inputs through a pipeline."""
    pl = Pipeline(pipe)
    return pl.run(inputs, *a, **kw)


if __name__ == '__main__':

    from datetime import datetime

    #from labrad.util import timing

    def delayedWakeup(t, data=None):
        return Future(util.wakeupCall, t, data)

    startReactor()

    def pipe1(i):
        for k in range(10):
            r = yield Priority(10-k), delayedWakeup(0.1 * k, k)
        returnValue(i)

    letters = [chr(65+n) for n in range(10)]

    pl = PipelineBase(pipe1)
    #t1 = timing(pl.run, n=1, inputs=range(10))

    pl = Pipeline(pipe1)
    #t2 = timing(pl.run, n=1, inputs=range(10))

    print 'pipe 1.'
    #print 'without prioritization: %g s' % t1
    #print 'with prioritization: %g s' % t2

    def pipe2(i):
        a = 0
        for x in range(50000000):
            a += 1
        yield LAST
        yield FIRST, delayedWakeup(5)
        returnValue(i)

    pl = PipelineBase(pipe2)
    #t1 = timing(pl.run, n=1, inputs=range(10))

    pl = Pipeline(pipe2)
    #t2 = timing(pl.run, n=1, inputs=range(10))

    print
    print 'pipe 2.'
    #print 'without prioritization: %g s' % t1
    #print 'with prioritization: %g s' % t2

    stopReactor()
