import labrad

#cxn = labrad.connect(backend='twisted')
#print cxn.python_test_server.settings

#cxn = labrad.connect('localhost', backend='asyncore', password='wrong')

cxn = labrad.connect(backend='asyncore', password='wrong')
