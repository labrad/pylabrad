#!/usr/bin/python
'''
Run the labrad node service through python, rather than through twistd.

For this to work, the node must be installed as a twistd service;
see pylabrad/twisted/plugins/labrad_node.py

For documentation on the node, see the top of its source file:
pylabrad/labrad/node/__init__.py
'''

from twisted.scripts.twistd import run
from sys import argv
argv[1:] = ['-n', 'labradnode']
run()
