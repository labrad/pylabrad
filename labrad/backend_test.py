import labrad

cxn = labrad.connect(backend='twisted')

print cxn.python_test_server.settings