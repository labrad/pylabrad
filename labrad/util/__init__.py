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

import copy, re, textwrap

from twisted.internet import defer, reactor
from twisted.python import log, reflect, util

from labrad import constants as C
from labrad.support import getNodeName
from labrad.util.unwrap import unwrap

def fancyHelp(ID, name, accepts, returns, units, about):
    """Create informative help text for a server setting.
    """
    accepts = createTypeStr(accepts)
    returns = createTypeStr(returns)

    helptext = """
%(ID)d - %(name)s

ACCEPTED TYPES:
%(accepts)s

RETURNED TYPES:
%(returns)s

UNITS:
%(units)s

NOTES:
%(about)s""" % {'ID': ID, 'name': name, 'accepts': accepts,
                'returns': returns, 'units': units, 'about': about}
    return helptext

def createTypeStr(typelist):
    """Create a text list of accepted and returned types."""
    if len(typelist) == 0:
        return 'Any'
    return '[%s]' % ', '.join(descStr(item) for item in typelist)

def descStr(item):
    if isinstance(item, str):
        return item
    elif isinstance(item, tuple):
        return '%s (%s)' % (item[0].__name__, item[1])
    else:
        return item.__name__

DOC_PATTERN = re.compile(r'(.*)NOTES?:\s*(.*)', re.DOTALL)
def parseSettingDoc(s):
    if s is None:
        return '', ''
    lines = s.split('\n')
    first, rest = lines[0].strip(), lines[1:]
    rest = textwrap.dedent('\n'.join(rest))
    s = first + '\n' + rest
    try:
        descr, notes = DOC_PATTERN.search(s).groups()
    except:
        descr, notes = s, ''
    return unwrap(descr.strip()), unwrap(notes)


# a list of printable representations of the ascii character codes
FILTER = ''.join(chr(x) if len(repr(chr(x)))==3 else '.' for x in range(256))

def dump(src, length=16):
    """Nicely-formatted hex dump of raw data."""
    N = 0; result = ''
    while src:
        s, src = src[:length], src[length:]
        hexa = ' '.join('%02X' % ord(x) for x in s)
        s = s.translate(FILTER)
        result += '%04X   %-*s   %s\n' % (N, length*3, hexa, s)
        N += length
    return result

def linspace(star, stop, N):
    """Linearly-spaced list of numbers."""
    return [star + (stop - star) * n / (N-1) for n in range(N)]

class ContextDict(dict):
    """Subclass of dict for holding context data.

    Using a subclass allows us to set attributes: ID and source.
    """

def findEnvironmentVars(string):
    """Find all environment variables of the form %VAR% in a string."""
    return re.findall('%([^%]+)%', string)

def interpEnvironmentVars(string, env=None):
    """Replace all environment variables of the form %VAR% in a string.
    
    Values are taken from the env variable, a dict-like object.  Variable
    names are converted to upper case before interpolation, to maintain
    case insensitivity.  If any required variables are not found in env,
    this raises a KeyError.
    """
    if env is None:
        import os
        env = os.environ
    for label in findEnvironmentVars(string):
        tag = '%' + label + '%'
        string = string.replace(tag, env[label.upper()])
    return string

def timedeltaToSeconds(td):
    return td.seconds + td.microseconds / 1.0e6

def timing(f, n=100, **kw):
    from datetime import datetime

    total = 0
    for _ in xrange(n):
        start = datetime.now()
        f(**kw)
        end = datetime.now()
        delta = end - start
        total += timedeltaToSeconds(delta)
    avg = total / float(n)
    return avg



# convenience functions for dealing with units
def convert(v, u):
    """Convert quantity v into units u.
    
    If v is just a number, no conversion is performed.
    If u is None, then the units of v are simply stripped
    but otherwise no conversion is performed.
    """
    if hasattr(v, 'value'): # prefer over subclass check: isinstance(v, Value)
        if u is None:
            return v.value
        else:
            return v[u]
    else:
        return v

def convertUnits(**unitdict):
    """
    Decorator to create functions that automatically
    convert arguments into specified units.  If a unit
    is specified for an argument and the caller passes
    an argument with incompatible units, an Exception
    will be raised.  Inside the decorated function, the
    arguments no longer have any units, they are just
    plain floats.  Not all arguments to the function need
    to be specified in the decorator.  Those that are not
    specified will be passed through unmodified.
    
    Usage:
    
    @convertUnits(t0='ns', amp=None)
    def func(t0, amp):
        <do stuff>
        
    This is essentially equivalent to:
    
    def func(t0, amp):
        t0 = convert(t0, 'ns')
        amp = convert(amp, None)
        <do stuff>
        
    The convert function, defined above, will convert
    any quantities with units into the specified units,
    or strip off any units if unit is None.
    """
    
    def wrap(f):
        args = inspect.getargspec(f)[0] # list of argument names
        for arg in unitdict:
            if arg not in args:
                raise Exception('function %s does not take arg "%s"' % (f, arg))
        # unitdict maps argument names to units
        # posdict maps argument positions to units
        posdict = dict((i, unitdict[arg]) for i, arg in enumerate(args) if arg in unitdict)
        
        @functools.wraps(f)
        def wrapped(*a, **kw):
            # convert positional arguments if they have a unit
            a = [convert(val, posdict.get(i, None)) for i, val in enumerate(a)]
            # convert named arguments if they have a unit
            for arg, val in kw.iteritems():
                if arg in unitdict:
                    kw[arg] = convert(val, unitdict[arg])
            # call the function with converted arguments
            return f(*a, **kw)
        return wrapped
    return wrap





# deferred helpers

def wakeupCall(delay, args=None):
    """Return a deferred that will be called back
    after a specified delay.
    """
    d = defer.Deferred()
    reactor.callLater(delay, d.callback, args)
    return d

def firstToFire(n=2):
    heads = [defer.Deferred() for _ in range(n)]
    first = defer.DeferredList(heads, fireOnOneCallback=True,
                                      fireOnOneErrback=True,
                                      consumeErrors=True)
    first.addCallback(lambda result: result[0])
    return first, heads

def maybeTimeout(deferred, timeout, timeoutResult):
    """Takes a deferred and returns a new deferred that might timeout."""
    td = defer.Deferred()
    reactor.callLater(timeout, td.callback, timeoutResult)
    d = defer.DeferredList([deferred, td], fireOnOneCallback=True,
                                           fireOnOneErrback=True,
                                           consumeErrors=True)
    d.addCallback(lambda (result, index): result)
    return d

class DeferredSignal(object):
    """An object that can create multiple deferreds on demand.
    
    When the signal is fired, all created deferreds will be fired
    or have their errback method called, as appropriate.
    """
    def __init__(self):
        self.waiters = []
        self.listeners = []
        self.fired = None
        
    def callback(self, data=None):
        self._fire(True, data)

    def errback(self, reason=None):
        self._fire(False, reason)

    def _fire(self, success, data):
        self.fired = success, data
        waiters = self.waiters
        self.waiters = []
        for d in waiters:
            if success:
                d.callback(data)
            else:
                d.errback(data)
        if success:
            for func in self.listeners:
                func(data)
        
    def __call__(self):
        if self.fired:
            success, data = self.fired
            if success:
                return defer.succeed(data)
            else:
                return defer.fail(data)
        else:
            d = defer.Deferred()
            self.waiters.append(d)
            return d
    
    def connect(self, listener):
        if listener not in self.listeners:
            self.listeners.append(listener)

    def disconnect(self, listener):
        self.listeners.remove(listener)


# run labrad server

def runServer(srv):
    """Run a server of the specified class."""
    
    import os, sys, time
    from twisted.internet import reactor
    from twisted.python import usage

    class ServerOptions(usage.Options):
        optParameters = [['name', 'n', srv.name, 'Server name.'],
                         ['node', 'd', getNodeName(), 'Node name.'],
                         ['port', 'p', C.MANAGER_PORT, 'Manager port.'],
                         ['host', 'h', C.MANAGER_HOST, 'Manager location.'],
                         ['password', 'w', C.PASSWORD, 'Login password.']]

    config = ServerOptions()
    try:
        config.parseOptions()
    except usage.UsageError, errortext:
        print '%s: %s' % (sys.argv[0], errortext)
        print '%s: Try --help for usage details.' % (sys.argv[0])
        sys.exit(1)

    def _ensureReactorStop():
        try:
            reactor.stop()
        except RuntimeError:
            pass

    def _disconnect(data):
        log.msg('Disconnected cleanly.')
        _ensureReactorStop()

    def _error(failure):
        log.msg('There was an error: ' + failure.getErrorMessage())
        _ensureReactorStop()

    srv.onStartup().addErrback(_error)
    srv.onShutdown().addCallbacks(_disconnect, _error)

    if config['name']:
        srv.name = config['name']
    env = dict(os.environ)
    env['LABRADNODE'] = config['node']
    srv.name = interpEnvironmentVars(srv.name, env)
    if hasattr(srv, 'instanceName'):
        srv.instanceName = interpEnvironmentVars(srv.instanceName, env)

    srv.password = config['password']

    log.startLogging(sys.stdout)
    #observer = MyLogObserver(sys.stdout)
    #log.startLoggingWithObserver(observer.emit)
    reactor.connectTCP(config['host'], int(config['port']), srv)
    reactor.run()

class MyLogObserver(log.FileLogObserver):
    timeFormat = '%Y/%m/%d %H:%M -'

    def emit(self, eventDict):
        edm = eventDict['message']
        if not edm:
            if eventDict['isError'] and 'failure' in eventDict:
                text = ((eventDict.get('why') or 'Unhandled Error')
                        + '\n' + eventDict['failure'].getTraceback())
            elif 'format' in eventDict:
                text = self._safeFormat(eventDict['format'], eventDict)
            else:
                # we don't know how to log this
                return
        else:
            text = ' '.join(map(reflect.safe_str, edm))

        timeStr = self.formatTime(eventDict['time'])
        fmtDict = {'text': text.replace("\n", "\n\t")}
        msgStr = self._safeFormat("%(text)s\n", fmtDict)

        util.untilConcludes(self.write, timeStr + " " + msgStr)
        util.untilConcludes(self.flush)  # Hoorj!

