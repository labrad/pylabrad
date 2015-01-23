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
from labrad.server import LabradServer, setting, Signal
from twisted.internet import defer, reactor
from twisted.internet.defer import returnValue
from twisted.python import log

from datetime import datetime

class TestServer(LabradServer):
    """Server to test labrad from python.

    This server provides a number of settings that
    are useful for testing labrad code, network profiling,
    and testing the python labrad library.
    """
    name = 'Dying Test Server'
    testMode = True

    def initServer(self):
        raise Exception()

    def serverConnected(self, data):
        print 'connected:', data

    def serverDisconnected(self, data):
        print 'disconnected:', data

    log = Signal(555, 'log', '(ts)')

    @setting(2)
    def delayed_echo(self, c, data):
        """Echo a packet after a specified delay."""
        yield util.wakeupCall(c['delay'])
        returnValue(data)

    @setting(3)
    def delayed_echo_deferred(self, c, data):
        """Echo a packet after a specified delay."""
        d = defer.Deferred()
        reactor.callLater(c['delay'], d.callback, data)
        return d

    @setting(4, delay=['v[s]', ''], returns=['v[s]'])
    def echo_delay(self, c, delay):
        """Get or set the echo delay."""
        log.msg('Echo delay: %s' % delay)
        self.log((datetime.now(), 'Echo delay: %s' % delay))
        if delay is not None:
            c['delay'] = float(delay)
        return c['delay']

    @setting(40, speed=['v[m/s]', ''], returns=['v[m/s]'])
    def speed(self, c, speed):
        """Get or set the speed."""
        log.msg('Speed: %s' % speed)
        self.log((datetime.now(), 'Speed: %s' % speed))
        if speed is not None:
            c['speed'] = speed
        return c['speed']

    @setting(41)
    def verbose_echo(self, c, data):
        print type(data)
        print repr(data)
        return data

    @setting(5)
    def exc_in_handler(self, c, data):
        log.msg('Exception in handler.')
        raise Exception('Raised in handler.')

    @setting(6)
    def exc_in_subfunction(self, c, data):
        log.msg('Exception in subfunction.')
        owie()

    @setting(7)
    def exc_in_deferred(self, c, data):
        log.msg('Exception in deferred.')
        d = defer.Deferred()
        d.addCallback(owie)
        reactor.callLater(1, d.callback, None)
        return d

    @setting(8)
    def exc_in_errback(self, c, data):
        log.msg('Exception from an errback.')
        d = defer.Deferred()
        reactor.callLater(1, d.errback, Exception('Raised by errback.'))
        return d

    @setting(9)
    def exc_in_inlinecallback(self, c, data):
        log.msg('Exception from an inlineCallback.')
        yield util.wakeupCall(c['delay'])
        raise Exception('Raised in inlineCallback.')

    @setting(10, returns=['s'])
    def bad_return_type(self, c, data):
        return 5

def owie(dummy=None):
    raise Exception('Raised in subfunction.')

__server__ = TestServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
