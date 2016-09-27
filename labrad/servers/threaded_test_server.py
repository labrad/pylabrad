"""
### BEGIN NODE INFO
[info]
name = Python Threaded Test Server
version = 1.0.0
description = Basic python server.

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 5
### END NODE INFO
"""

import time

from labrad import types as T, util
from labrad.server import ThreadedServer, setting
from labrad.units import m, s
from labrad.util import hydrant


class TestServer(ThreadedServer):
    """Server to test labrad from python.

    This server provides a number of settings that
    are useful for testing labrad code, network profiling,
    and testing the python labrad library.
    """
    name = 'Python Threaded Test Server'
    testMode = True
    shutdownMessage = 987654321

    def initServer(self):
        time.sleep(0.5)

    def stopServer(self):
        print 'before sleep'
        time.sleep(0.5)
        print 'after sleep'

    def serverConnected(self, ID, name):
        print 'server connected:', ID, name

    def serverDisconnected(self, ID, name):
        print 'server disconnected:', ID, name

    def initContext(self, c):
        c['delay'] = 1*s
        c['dict'] = {}

    @setting(2, "Delayed Echo", data='?')
    def delayed_echo(self, c, data):
        """Echo a packet after a specified delay."""
        time.sleep(c['delay'][s])
        return data

    @setting(3, "Future Echo", data='?')
    def future_echo(self, c, data):
        """Echo a packet after a specified delay."""
        f = self.client.manager.echo.future(data)
        time.sleep(c['delay'][s])
        return f

    @setting(4, "Echo Delay", delay='v[s]', returns='v[s]')
    def echo_delay(self, c, delay=None):
        """Get or set the echo delay."""
        self.log('Echo delay: %s' % delay)
        if delay is not None:
            c['delay'] = delay
        return c['delay']

    @setting(2000, "Registry Dir", path='*s', returns='(*s, *s)')
    def registry_dir(self, c, path=['']):
        """Get Registry listing for the specified path."""
        p = self.client.registry.packet()
        p.cd([''])
        p.cd(path)
        p.dir()
        result = p.send()
        dirs, keys = result['dir']
        return dirs, keys

    @setting(42, "Delayed Echo Wrapper", data='?', returns='?')
    def delayed_echo_wrapper(self, c, data):
        """Echo a packet after a delay just like delayed_echo.

        This tests calling a setting from another setting.
        """
        rv = self.delayed_echo(c, data)
        return rv

    @setting(40, "Speed", speed='v[m/s]', returns='v[m/s]')
    def speed(self, c, speed=None):
        """Get or set the speed."""
        self.log('Speed: %s' % speed)
        if speed is not None:
            c['speed'] = speed
        return c['speed']

    @setting(41, "Verbose Echo", data='?')
    def verbose_echo(self, c, data):
        print type(data)
        print repr(data)
        return data

    @setting(5, "Exc in Handler", data='?')
    def exc_in_handler(self, c, data):
        """Raises an exception directly in the handler."""
        self.log('Exception in handler.')
        raise Exception('Raised in handler.')

    @setting(9, "Exc after delay", data='?')
    def exc_in_inlinecallback(self, c, data):
        """Raises an exception after a delay."""
        self.log('Exception after delay.')
        time.sleep(c['delay'][s])
        raise Exception('Raised after delay.')

    @setting(10, "Bad Return Type", data='?', returns='s')
    def bad_return_type(self, c, data):
        """Returns a value that does not match the declared return type."""
        return 5

    @setting(11, "Get Random Data", tag='s')
    def get_random_data(self, c, tag=None):
        """Get a random bit of data conforming to the specified type tag."""
        if tag is None:
            t = hydrant.randType()
        else:
            t = T.parseTypeTag(tag)
        return hydrant.randValue(t)

    @setting(12, "Get Random Tag")
    def get_random_tag(self, c):
        """Get a random LabRAD type tag."""
        return str(hydrant.randType())

    @setting(100, "Set", unflatten=False, key='s', value='?', returns='')
    def set(self, c, key, value):
        c['dict'][key.unflatten()] = value

    @setting(101, "Get", key='s', returns='?')
    def get(self, c, key):
        print "getting tag: %s, value: %s" % (key, c['dict'][key])
        return c['dict'][key]

    @setting(102, "Keys", returns='*s')
    def keys(self, c):
        return sorted(c['dict'].keys())

    @setting(103, "Set Reversed", value='?', key='s', unflatten=False)
    def set_reversed(self, c, value, key):
        """Same as self.set() with argument order reversed."""
        self.set(c, key, value)

    @setting(1000, path=['', 's'], file=['s'])
    def first_arg_can_have_default_value(self, c, path=None, file=None):
        """Exercise setting decorator fix from issue #242."""
        pass


if __name__ == '__main__':
    util.runServer(TestServer())
