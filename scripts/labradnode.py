#!/usr/bin/python
'''
Run the labrad node service through python, rather than through twistd.
'''

from twisted.scripts.twistd import run
from sys import argv
argv[1:] = ['-n', 'labradnode']
run()
