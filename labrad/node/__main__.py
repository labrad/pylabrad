"""
Run a node service for controlling other labrad servers.

This files makes it possible to run the node as an executable module:

`python -m labrad.node`
"""

import labrad.node

labrad.node.main()
