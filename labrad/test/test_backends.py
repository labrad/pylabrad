import unittest

from labrad import backend
from labrad.errors import LoginFailedError


# class AsyncoreBackendTests(unittest.TestCase):
#     def testConnection(self):
#         cxn = backend.AsyncoreConnection()
#         cxn.connect()
#         self.assertTrue(cxn.loop.is_alive())
#         cxn.disconnect()
#         self.assertFalse(cxn.loop.is_alive())
# 
#     def testBadHostExceptions(self):
#         cxn = backend.AsyncoreConnection()
#         self.assertRaises(LoginFailedError, cxn.connect, host='bad.host.com', timeout=1)
#         self.assertFalse(hasattr(cxn, 'loop'))
# 
#     def testBadPasswordException(self):
#         cxn = backend.AsyncoreConnection()
#         self.assertRaises(LoginFailedError, cxn.connect, password='bad password', timeout=1)
#         self.assertFalse(cxn.connected)
#         # event loop should terminate
#         cxn.loop.join(1)
#         self.assertFalse(cxn.loop.is_alive())
# 
#     def testRequestCancellation(self):
#         cxn = backend.AsyncoreConnection()
#         cxn.connect()
#         cxn.sendRequest(1, [(1, None, '_')]).result()
#         future = cxn.sendRequest(1, [(1, None, '_')])
#         self.assertTrue(cxn.loop.is_alive())
#         cxn.disconnect()
#         self.assertFalse(cxn.loop.is_alive())
#         self.assertRaises(Exception, future.result)
# 
#     def testConnectionDrop(self):
#         badPacket = (
#             b'\x00\x00\x00\x00\x00\x00\x00\x00' # context
#             b'\x00\x00\x00\x01' # request
#             b'\x00\x00\x00\x01' # target
#             b'\x00\x00\x00\x08' # data length
#             b'\x00\x00\x00\x00' # id
#             b'\x00\x00\x00\x04' # tag string claims to have four bytes
#         )
# 
#         cxn = backend.AsyncoreConnection()
#         cxn.connect()
#         self.assertTrue(cxn.loop.is_alive())
#         cxn.sendRequest(1, [(1, None, '_')]).result()
#         cxn.cxn.queue.put(badPacket)
#         cxn.cxn.queue.put(badPacket) # this will cause the manager to drop us...
#         # we send a request in a subfunction because the exception can be raised
#         # either in the sendRequest call or in the wait call, depending on timing
#         def doRequest():
#             cxn.sendRequest(1, [(1, None, '_')]).result()
#         self.assertRaises(Exception, doRequest)
#         self.assertRaises(Exception, doRequest)

