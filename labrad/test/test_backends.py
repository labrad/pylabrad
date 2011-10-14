import unittest

from labrad import backend
from labrad.errors import LoginFailedError

class AsyncoreBackendTests(unittest.TestCase):
    def testConnection(self):
        cxn = backend.AsyncoreConnection()
        cxn.connect()
        self.assertTrue(cxn.loop.is_alive())
        cxn.disconnect()
        self.assertTrue(not cxn.loop.is_alive())

    def testBadHostExceptions(self):
        cxn = backend.AsyncoreConnection()
        self.assertRaises(LoginFailedError, cxn.connect, host='bad.host.com', timeout=1)
        self.assertTrue(not hasattr(cxn, 'loop'))
        
    def testBadPasswordException(self):
        cxn = backend.AsyncoreConnection()
        self.assertRaises(LoginFailedError, cxn.connect, password='bad password', timeout=1)
        self.assertTrue(not cxn.loop.is_alive())
        
    def testRequestCancellation(self):
        cxn = backend.AsyncoreConnection()
        cxn.connect()
        cxn.sendRequest(1, [(1L, None)]).wait()
        future = cxn.sendRequest(1, [(1L, None)])
        self.assertTrue(cxn.loop.is_alive())
        cxn.disconnect()
        self.assertTrue(not cxn.loop.is_alive())
        self.assertRaises(Exception, future.wait)
        
    def testConnectionDrop(self):
        badPacket = (
            '\x00\x00\x00\x00\x00\x00\x00\x00' # context
            '\x00\x00\x00\x01' # request
            '\x00\x00\x00\x01' # target
            '\x00\x00\x00\x08' # data length
            '\x00\x00\x00\x00' # id
            '\x00\x00\x00\x04' # tag string claims to have four bytes
        )
        
        cxn = backend.AsyncoreConnection()
        cxn.connect()
        self.assertTrue(cxn.loop.is_alive())
        cxn.sendRequest(1, [(1L, None)]).wait()
        cxn.cxn.queue.put(badPacket)
        cxn.cxn.queue.put(badPacket) # this will cause the manager to drop us...
        # we send a request in a subfunction because the exception can be raised
        # either in the sendRequest call or in the wait call, depending on timing
        def doRequest():
            cxn.sendRequest(1, [(1L, None)]).wait()
        self.assertRaises(Exception, doRequest)
        self.assertRaises(Exception, doRequest)
        
