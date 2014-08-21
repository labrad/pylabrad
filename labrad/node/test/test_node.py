from labrad.node import *
from twisted.trial import unittest
import os
from socket import gethostname
#from twisted.internet.base import DelayedCall
#DelayedCall.debug = True

class NodeTestCase(unittest.TestCase):
    
    def setUp(self):
        import labrad
        #self.cxn = labrad.connect()
        #self.addCleanup(self.cxn.disconnect)
        name = os.environ.get('LABRADNODE', gethostname()) + '_test'
        self.node = Node(name,
            labrad.constants.MANAGER_HOST,
            labrad.constants.MANAGER_PORT)
        self.node.startService()
        #self.addCleanup(self.node.stopService)
    
    def test_nothing(self):
        self.assertEqual(3, 3)
        #import time
        #time.sleep(3)

    def tearDown(self):
        return self.node.stopService()
