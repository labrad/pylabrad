from twisted.trial import unittest

from labrad import backend
from labrad.errors import LoginFailedError

class BackendTests(unittest.TestCase):
    def testAsyncoreConnection(self):
        cxn = backend.AsyncoreConnection()
        cxn.connect()
        self.assertTrue(cxn._loop.is_alive())
        cxn.disconnect()
        self.assertTrue(not cxn._loop.is_alive())

    def testAsyncoreExceptions(self):
        cxn = backend.AsyncoreConnection()
        self.assertRaises(LoginFailedError, cxn.connect, host='bad host')
        self.assertTrue(not cxn._loop.is_alive())
        
        cxn = backend.AsyncoreConnection()
        self.assertRaises(LoginFailedError, cxn.connect, password='bad password')
        self.assertTrue(not cxn._loop.is_alive())

        