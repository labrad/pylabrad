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
import contextlib
import os
import sys

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.threads import blockingCallFromThread
from twisted.python import log, reflect, util

from labrad import constants as C, crypto, support, thread
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
FILTER = ''.join(chr(x) if len(repr(chr(x))) == 3 else '.' for x in range(256))

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


def is_local_connection(transport):
    """Determine whether the given network transport is connected to localhost.

    Args:
        transport (twisted.internet.interfaces.ITransport): a twisted transport
            object, representing a network connection.

    Returns (boolean):
        True if the transport is connected to a peer on the local host, False
        otherwise.
    """
    remote_addr = transport.getPeer().host
    local_addr = transport.getHost().host
    return remote_addr in ['127.0.0.1', '::1'] or remote_addr == local_addr


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

@inlineCallbacks
def maybeTimeout(deferred, timeout, timeoutResult):
    """Takes a deferred and returns a new deferred that might timeout."""
    td = wakeupCall(timeout, timeoutResult)
    result, _index = yield defer.DeferredList([deferred, td],
                                              fireOnOneCallback=True,
                                              fireOnOneErrback=True,
                                              consumeErrors=True)
    returnValue(result)

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

def parseServerOptions(name, exit_on_failure=True, options=None):
    """Parse standard command line options for a server.

    Args:
        name (string): The default server name to use if no name is specified
            on the command line.
        exit_on_failure (boolean): If True, we call sys.exit when we fail
            to parse the command line options. Otherwise, we raise UsageError.
        options (list(string)): If given, parse options from the given strings.
            Otherwise, will parse options from the command line in sys.argv.

    Returns:
        A ServerOptions instance initialized from the command line arguments.
        This is a dict-like object containing these string-valued keys:
            'name', 'node', 'host', 'port', 'password', 'tls'
    """
    from twisted.python import usage

    class ServerOptions(usage.Options):
        optParameters = [
            ['name', 'n', name, 'Server name.'],
            ['node', 'd', getNodeName(), 'Node name.'],
            ['host', 'h', C.MANAGER_HOST, 'Manager location.'],
            ['port', 'p', None, 'Manager port.', int],
            ['password', 'w', None, 'Login password.'],
            ['tls', 's', C.MANAGER_TLS,
             'TLS mode for connecting to manager (on/starttls/off)']]

    config = ServerOptions()
    config['tls'] = C.check_tls_mode(config['tls'])
    try:
        config.parseOptions(options=options)
        if config['password'] is None:
            config['password'] = support.get_password(host=config['host'],
                                                      port=config['port'],
                                                      prompt=False)
        if config['port'] is None:
            tls_on = config['tls'] == 'on'
            config['port'] = C.MANAGER_PORT_TLS if tls_on else C.MANAGER_PORT
    except usage.UsageError, errortext:
        print '%s: %s' % (sys.argv[0], errortext)
        print '%s: Try --help for usage details.' % (sys.argv[0])
        if exit_on_failure:
            sys.exit(1)
        else:
            raise
    return config

def updateServerOptions(srv, config):
    """Update server options (name, instanceName, password) from cmdline config.

    Args:
        srv: An instance of LabradServer to be updated to match the config.
        config: A dict-like object containing keys 'name', 'instanceName' and
            'password'. Typically, this will be a ServerOptions instance
            returned by parseServerOptions.
    """
    if config['name']:
        srv.name = config['name']
    env = dict(os.environ)
    env['LABRADNODE'] = config['node']
    srv.name = interpEnvironmentVars(srv.name, env)
    if hasattr(srv, 'instanceName'):
        srv.instanceName = interpEnvironmentVars(srv.instanceName, env)

def runServer(srv, run_reactor=True, stop_reactor=True):
    """Run the given server instance.

    Args:
        srv (LabradServer): The server instance to run.
        run_reactor (boolean): If True, we call reactor.run() to start the
            twisted reactor. Otherwise, the caller must ensure that reactor.run
            is called.
        stop_reactor (boolean): If True, we call reactor.stop() after the
            server instance shuts down (whether normally or due to an error
            condition. Otherwise, the caller must arrange to call reactor.stop.
    """
    from labrad import protocol
    from twisted.internet import reactor

    config = parseServerOptions(name=srv.name)
    updateServerOptions(srv, config)

    log.startLogging(sys.stdout)
    #observer = MyLogObserver(sys.stdout)
    #log.startLoggingWithObserver(observer.emit)

    @inlineCallbacks
    def run(srv):
        host = config['host']
        port = int(config['port'])
        tls_mode = config['tls']
        try:
            p = yield protocol.connect(host, port, tls_mode)
            yield p.authenticate(config['password'])
            yield srv.startup(p)
            yield srv.onShutdown()
            log.msg('Disconnected cleanly.')
        except Exception as e:
            log.msg('There was an error: {}'.format(e))
        if stop_reactor:
            try:
                reactor.stop()
            except Exception:
                pass

    _ = run(srv)
    if run_reactor:
        reactor.run()

@contextlib.contextmanager
def syncRunServer(srv, host=C.MANAGER_HOST, port=None, password=None,
                  tls_mode=C.MANAGER_TLS):
    """Run a labrad server of the specified class in a synchronous context.

    Returns a context manager to be used with python's with statement that
    will yield when the server has started and then shut the server down after
    the context is exited.
    """
    from labrad import protocol

    tls_mode = C.check_tls_mode(tls_mode)

    if port is None:
        port = C.MANAGER_PORT_TLS if tls_mode == 'on' else C.MANAGER_PORT

    if password is None:
        password = C.PASSWORD

    @inlineCallbacks
    def start_server():
        p = yield protocol.connect(host, port, tls_mode)
        yield p.authenticate(password)
        yield srv.startup(p)

    @inlineCallbacks
    def stop_server():
        srv.disconnect()
        yield srv.onShutdown()

    thread.startReactor()
    blockingCallFromThread(reactor, start_server)
    try:
        yield
    finally:
        try:
            blockingCallFromThread(reactor, stop_server)
        except Exception:
            pass # don't care about exceptions here



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

