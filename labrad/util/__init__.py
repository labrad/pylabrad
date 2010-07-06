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

from twisted.internet import defer, reactor
from twisted.python import failure, log, reflect, util
from twisted.python.util import mergeFunctionMetadata
import copy, re, textwrap
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

ALLOWED = 'abcdefghijklmnopqrstuvwxyz1234567890_'
FIRST = 'abcdefghijklmnopqrstuvwxyz_'

def mangle(name):
    """Return a modified string that is usable as a method name."""
    newname = ''.join(c if c in ALLOWED else '_' for c in name.lower())
    if newname[0] not in FIRST:
        newname = '_' + newname
    return newname

def indent(s, level=1):
    spc = ' ' * (4 * level)
    return '\n'.join(spc + line for line in s.split('\n'))

def linspace(star, stop, N):
    """Linearly-spaced list of numbers."""
    return [star + (stop - star) * n / (N-1) for n in range(N)]

def wakeupCall(delay, args=None):
    """Return a deferred that will be called back
    after a specified delay.
    """
    d = defer.Deferred()
    reactor.callLater(delay, d.callback, args)
    return d

def extractKey(d, key, default):
    if key not in d:
        return default
    val = d[key]
    del d[key]
    return val

class SafeIterDict(dict):
    """A dict subclass that allows insertion and deletion while iterating.
    
    This is accomplished by overriding keys, items, values, etc. to return
    copies of their respective lists, rather than the lists themselves.
    Note that this negates the efficiency gains of using the iter* methods.
    """
    keys = lambda self: list(dict.keys(self))
    items = lambda self: list(dict.items(self))
    values = lambda self: list(dict.values(self))
    iterkeys = lambda self: iter(self.keys())
    iteritems = lambda self: iter(self.items())
    itervalues = lambda self: iter(self.values())
    __iter__ = lambda self: iter(self.keys())

class MultiDict(SafeIterDict):
    """Dictionary with multiple keys to the same value."""
    def __init__(self, *a, **kw):
        dict.__init__(self, *a, **kw)
        self.aliases = {} # mapping from aliases to keys
        self._keys = {} # mapping from keys to aliases

    def __repr__(self):
        items = []
        for k, v in self.iteritems():
            key_str = repr(k)
            if k in self._keys:
                aliases = [key_str] + [repr(a) for a in self._keys[k]]
                key_str = ' or '.join(aliases)
            items.append('%s: %r' % (key_str, v))
        return '{' + ', '.join(items) + '}'

    def __setitem__(self, k, v):
        if isinstance(k, tuple):
            k, aliases = k[0], k[1:]
            for alias in aliases:
                self.aliases[alias] = k
            self._keys[k] = aliases
        dict.__setitem__(self, k, v)

    def __delitem__(self, k):
        if k in self.aliases:
            k = self.aliases[k]
        # delete aliases for this key
        if k in self._keys:
            aliases = self._keys[k]
            for a in aliases:
                # only delete alias if it still points to this key
                if self.aliases[a] == k:
                    del self.aliases[a]
            del self._keys[k]
        dict.__delitem__(self, k)

    def __contains__(self, k):
        if k in self.aliases:
            k = self.aliases[k]
        return dict.__contains__(self, k)

    def __getitem__(self, k):
        if k in self.aliases:
            k = self.aliases[k]
        return dict.__getitem__(self, k)
    
    def _updateAliases(self, k, *aliases):
        """Update the aliases for a given key."""
        for a in set(self._keys[k]) - set(aliases):
            # remove old aliases, but only if they still
            # point to this key
            if self.aliases[a] == k:
                del self.aliases[a]
        for a in aliases:
            self.aliases[a] = k
        self._keys[k] = aliases

class PrettyMultiDict(MultiDict):
    def __repr__(self):
        return '\n'.join(sorted(self.keys()))

class ContextDict(dict):
    """Subclass of dict for holding context data.

    Using a subclass allows us to set attributes: ID and source.
    """


from labrad import constants as C

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

class MyLogObserver(log.FileLogObserver):
    timeFormat = '%Y/%m/%d %H:%M -'

    def emit(self, eventDict):
        edm = eventDict['message']
        if not edm:
            if eventDict['isError'] and eventDict.has_key('failure'):
                text = ((eventDict.get('why') or 'Unhandled Error')
                        + '\n' + eventDict['failure'].getTraceback())
            elif eventDict.has_key('format'):
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

def getNodeName():
    import os, socket
    return os.environ.get('LABRADNODE', socket.gethostname().lower())

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
