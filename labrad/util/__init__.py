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

import argparse
import asyncio
import copy
import datetime
import os
import re
import sys
import textwrap
import time

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
        env = os.environ
    for label in findEnvironmentVars(string):
        tag = '%' + label + '%'
        string = string.replace(tag, env[label.upper()])
    return string

def timedeltaToSeconds(td):
    return td.seconds + td.microseconds / 1.0e6

def timing(f, n=100, **kw):
    total = 0
    for _ in range(n):
        start = datetime.datetime.now()
        f(**kw)
        end = datetime.datetime.now()
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
            for arg, val in kw.items():
                if arg in unitdict:
                    kw[arg] = convert(val, unitdict[arg])
            # call the function with converted arguments
            return f(*a, **kw)
        return wrapped
    return wrap





# asyncio helpers

class DeferredSignal():
    """An object that can create multiple deferreds on demand.

    When the signal is fired, all created deferreds will be fired
    or have their errback method called, as appropriate.
    """
    def __init__(self):
        self.fired = asyncio.Event()

    def set_result(self, result=None):
        if self.fired.is_set():
            raise Exception('signal already fired')
        self.success = True
        self.result = result
        self.fired.set()

    def set_exception(self, exception=None):
        if self.fired.is_set():
            raise Exception('signal already fired')
        self.success = False
        self.exception = exception
        self.fired.set()

    @asyncio.coroutine
    def __call__(self):
        yield from self.fired.wait()
        if self.success:
            return self.result
        else:
            raise self.exception

# run labrad server

def run_server(srv):
    """Run a server of the specified class."""
    import labrad.protocol

    parser = argparse.ArgumentParser(description='Run the {} server'.format(srv.name))
    parser.add_argument('--name', default=srv.name, help='Server name.')
    parser.add_argument('--node', default=getNodeName(), help='Node name.')
    parser.add_argument('--port', default=C.MANAGER_PORT, help='Manager port.')
    parser.add_argument('--host', default=C.MANAGER_HOST, help='Manager location.')
    parser.add_argument('--password', default=C.PASSWORD, help='Login password.')
    config = parser.parse_args()

    if config.name:
        srv.name = config.name
    env = dict(os.environ)
    env['LABRADNODE'] = config.node
    srv.name = interpEnvironmentVars(srv.name, env)
    if hasattr(srv, 'instanceName'):
        srv.instanceName = interpEnvironmentVars(srv.instanceName, env)

    srv.password = config.password

    @asyncio.coroutine
    def run(loop):
        try:
            reader, writer = yield from asyncio.open_connection(host=config.host, port=config.port)
            cxn = labrad.protocol.AsyncioConnection(reader, writer, srv)
            try:
                yield from srv.start(cxn)
                yield from srv.onStartup()
                yield from srv.onShutdown()
                print('Disconnected cleanly.')
            except Exception as e:
                print('There was an error', e)
                cxn.close()
        finally:
            loop.stop()

    loop = asyncio.get_event_loop()
    loop.create_task(run(loop))
    loop.run_forever()
    loop.close()
