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
from twisted.python import failure
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

docStringPattern = re.compile(r'(.*)NOTES?:\s*(.*)', re.DOTALL)
def parseSettingDoc(s):
    if s is None:
        return '', ''
    lines = s.split('\n')
    first, rest = lines[0], lines[1:]
    first = first.strip()
    rest = textwrap.dedent('\n'.join(rest))
    s = first + '\n' + rest
    try:
        descr, notes = docStringPattern.search(s).groups()
    except:
        descr, notes = s, ''
    return unwrap(descr.strip()), unwrap(notes)


# a list of printable representations of the ascii character codes
FILTER=''.join([(len(repr(chr(x)))==3) and chr(x) or '.' for x in range(256)])

def dump(src, length=16):
    """Nicely-formatted hex dump of raw data."""
    N=0; result=''
    while src:
       s,src = src[:length],src[length:]
       hexa = ' '.join(["%02X"%ord(x) for x in s])
       s = s.translate(FILTER)
       result += "%04X   %-*s   %s\n" % (N, length*3, hexa, s)
       N+=length
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
    spc = '    '*level
    return '\n'.join([spc + line for line in s.split('\n')])

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
    if key in d:
        val = d[key]
        del d[key]
        return val
    else:
        return default

class DefaultDict(dict):
    """Dictionary with a default value for unknown keys."""
    def __init__(self, default={}):
        self.default = default

    def __getitem__(self, key):
        if key in self: return self.get(key)
        return self.setdefault(key, copy.deepcopy(self.default))

class MultiDict(dict):
    """Dictionary with multiple keys to the same value."""
    def __init__(self, *a, **kw):
        dict.__init__(self, *a, **kw)
        self.aliases = {}
        self._keys = {}

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
        if k in self._keys:
            aliases = self._keys[k]
            for a in aliases:
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

class PrettyDict(MultiDict):
    def __repr__(self):
        names = self.keys()
        names.sort()
        return '\n'.join(names)

class ContextDict(dict):
    """Subclass of dict for holding context data.

    Allows us to set attributes like ID."""
    pass


from twisted.python import usage
from labrad import constants as C

def runServer(srv):
    """Run a server of the specified class."""
    
    import sys, time
    from twisted.internet import reactor
    from twisted.python import log

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
        log.msg('Disconnected Cleanly.')
        _ensureReactorStop()

    def _error(failure):
        log.msg('There was an error: ' + failure.getErrorMessage())
        _ensureReactorStop()

    srv.startup().addErrback(_error)
    srv.shutdown().addCallbacks(_disconnect, _error)

    if config['name']:
        srv.name = config['name']
    srv.setName(localizeServerName(srv, config['node']))

    srv.password = config['password']

    log.startLogging(sys.stdout)
    reactor.connectTCP(config['host'], int(config['port']), srv)
    reactor.run()

def localizeServerName(server, node=None):
    if node is None:
        node = getNodeName()
    if hasattr(server, 'isLocal'):
        return node + ' ' + server.name
    else:
        return server.name

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
    def __init__(self):
        self.waiters = []
        self.listeners = []

    def callback(self, data=None):
        waiters = self.waiters
        self.waiters = []
        for d in waiters:
            d.callback(data)
        for listener in self.listeners:
            listener(data)

    def errback(self, reason=None):
        waiters = self.waiters
        self.waiters = []
        for d in waiters:
            d.errback(reason)

    def __call__(self):
        d = defer.Deferred()
        self.waiters.append(d)
        return d
    
    def connect(self, listener):
        if listener not in self.listeners:
            self.listeners.append(listener)

    def disconnect(self, listener):
        self.listeners.remove(listener)
