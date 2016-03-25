import unittest

import labrad
from labrad import types as T
from labrad.servers.test_server import TestServer
from labrad.util import syncRunServer

TEST_STR = 'this is a test, this is only a test'

class ClientTests(unittest.TestCase):
    def run(self, result=None):
        """Override the TestCase run method to launch the test server.

        This seems to be the cleanest solution for effectively using a
        context manager as part of a test fixture.  This method then calls
        the usual test fixture setUp and tearDown within this context.
        """
        with syncRunServer(TestServer()):
            super(ClientTests, self).run(result)

    def setUp(self):
        self.cxn = labrad.connect()

    def tearDown(self):
        self.cxn.disconnect()

    def _get_manager(self):
        self.assertTrue(hasattr(self.cxn, 'manager'))
        return self.cxn.manager

    def _get_tester(self):
        self.assertTrue(hasattr(self.cxn, 'python_test_server'))
        return self.cxn.python_test_server

    def testConnection(self):
        servers = self.cxn.servers
        self.assertTrue(len(servers.keys()) > 0)
        self.assertTrue('manager' in servers)
        self.assertTrue('python_test_server' in servers)

        self._get_manager()
        self._get_tester()

        self._get_manager()
        self._get_tester()

    def testServer(self):
        pts = self._get_tester()

        # make sure we can access the setting by both allowed methods
        self.assertTrue(hasattr(pts, 'echo'))
        self.assertTrue('echo' in pts.settings)

        # single setting, named explicitly
        resp = pts.echo(TEST_STR)
        self.assertEqual(resp, TEST_STR)

        resp = pts.echo(T.Value(15.0, 's'))
        self.assertEqual(resp['s'], 15.0)
        self.assertEqual(resp.unit.name, 's')

        # single setting with the name looked up
        resp = pts.settings['echo']([1, 2, 3, 4])
        self.assertEqual(len(resp), 4)

        # single setting with delayed response
        resp = pts.echo.future(TEST_STR)
        resp = resp.result()
        self.assertEqual(resp, TEST_STR)

        # allow .wait() for backwards compatibility
        resp = pts.echo.future(TEST_STR)
        resp = resp.wait()
        self.assertEqual(resp, TEST_STR)

        # allow calling with wait=False for backwards compatibility
        resp = pts.echo(TEST_STR, wait=False)
        resp = resp.result()
        self.assertEqual(resp, TEST_STR)

        resp = pts.echo(TEST_STR, wait=False)
        resp = resp.wait()
        self.assertEqual(resp, TEST_STR)


    def testCompoundPacket(self):
        pts = self._get_tester()

        self.assertTrue(hasattr(pts, 'packet'))

        # make a simple packet and check the various methods of getting
        # data out of it
        pkt = pts.packet()
        resp = pkt.echo(1).echo(2).settings['echo'](3).send()
        self.assertTrue(hasattr(resp, 'echo'))
        self.assertEqual(len(resp.echo), 3)
        self.assertTrue('echo' in resp.settings)
        self.assertEqual(len(resp.settings['echo']), 3)
        self.assertEqual(len(resp['echo']), 3)

        # test using keys to refer to parts of a packet
        pkt2 = pts.packet()
        resp = pkt2.echo(1L, key='one')\
                   .echo_delay(T.Value(0.1, 's'))\
                   .delayed_echo('blah', key='two')\
                   .send()
        self.assertTrue(hasattr(resp, 'one'))
        self.assertTrue('one' in resp.settings)
        self.assertEqual(resp['one'], 1)
        self.assertFalse(hasattr(resp, 'echo_word'))
        self.assertEqual(resp.two, 'blah')

        # test packet mutation by key
        pkt2['two'] = TEST_STR
        resp = pkt2.send()
        self.assertEqual(resp.two, TEST_STR)

        # send packet asynchronously
        resp = pkt2.send_future()
        resp = resp.result()
        self.assertEqual(resp.two, TEST_STR)

        # allow calling .wait() for backwards compatibility
        resp = pkt2.send_future()
        resp = resp.wait()
        self.assertEqual(resp.two, TEST_STR)

        # allow sending with wait=False for backwards compatibility
        resp = pkt2.send(wait=False)
        resp = resp.result()
        self.assertEqual(resp.two, TEST_STR)

        resp = pkt2.send(wait=False)
        resp = resp.wait()
        self.assertEqual(resp.two, TEST_STR)

    def testTupleKeys(self):
        # allow the use of tuples as packet keys
        pts = self._get_tester()

        p = pts.packet()
        p.echo(1, key='a')
        p.echo(2, key=(1, 2))
        r = repr(p)
        s = str(p)
        resp = p.send()
        self.assertEqual(resp.a, 1)
        self.assertEqual(resp['a'], 1)
        self.assertEqual(resp[(1, 2)], 2)

    def testExceptions(self):
        pts = self._get_tester()

        pts.echo_delay(T.Value(0.1, 's'))
        self.assertRaises(Exception, pts.exc_in_handler)
        self.assertRaises(Exception, pts.exc_in_subfunction)
        self.assertRaises(Exception, pts.exc_in_deferred)
        self.assertRaises(Exception, pts.exc_in_errback)
        self.assertRaises(Exception, pts.exc_in_inlinecallback)

    def testContextWrappers(self):
        cxn1 = self.cxn()
        cxn2 = self.cxn()

        pts1 = cxn1.python_test_server
        pts2 = cxn2.python_test_server
        pts3 = cxn1.python_test_server()
        pts4 = pts2()

        pts1.set('1', 1)
        pts2.set('2', 2)
        pts3.set('3', 3)
        pts4.set('4', 4)

        self.assertEqual(pts1.keys(), ['1'])
        self.assertEqual(pts2.keys(), ['2'])
        self.assertEqual(pts3.keys(), ['3'])
        self.assertEqual(pts4.keys(), ['4'])

    def test_server_calls(self):
        """Make sure that server settings can call other settings directly.
        """
        cxn = self.cxn()

        ts = cxn.python_test_server

        ts.set_reversed("bar", "foo")
        self.assertEqual(ts.get("foo"), "bar")

        ts.echo_delay(T.Value(0.1, 's'))
        self.assertEquals(ts.delayed_echo_wrapper(1), 1)

if __name__ == "__main__":
    unittest.main()
