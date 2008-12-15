# Copyright (C) 2007  Matthew Neeley
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
labrad module for python.
"""

from __future__ import with_statement
from contextlib import contextmanager

from labrad import client, constants as C, manager, util
from labrad.wrappers import connectAsync, runAsync

__version__  = '0.92.0'
__revision__ = '$Revision$'
__date__     = '$Date$'

# flag that determines whether we are in tutorial mode
tutorial_mode = False

#@contextmanager
#def connection(host=C.MANAGER_HOST, port=C.MANAGER_PORT,
#               name='Python Client', **kw):
#    try:
#        cxn = client.Client(name)
#        cxn.connect(host, port, **kw)
#        yield cxn
#    except KeyboardInterrupt:
#        pass # ignore keyboard interrupt exceptions
#    finally:
#        cxn.disconnect()

def connect(host=C.MANAGER_HOST, port=C.MANAGER_PORT, name=None, **kw):
    """Create a client connection to the labrad manager."""
    cxn = client.Client(name)
    cxn.connect(host, port, **kw)

    if tutorial_mode:
        print """\
Manager connection established successfully...

The following servers were found:
%s

You can create an alias name for your server using:
    <Server> = <Connection>.<Server Name>

To get information about the server just type its name:
    <Server>   or
    <Connection>.<Server Name>

To get information about a setting type:
    <Server>.<Setting>

To execute requests use
    <Server>.<Setting> (<Parameters>)
(Note: you need parenthesis even if there are no parameters,
       otherwise you will get the help-text again!)
""" % repr(cxn.servers)

    return cxn

connection = connect
    
def tutorial():
    global tutorial_mode
    tutorial_mode = True
    print """
First thing to do: connect to the labrad manager using the
labrad.connect function.  This function takes as an argument
the hostname of the computer where the manager is running.

>>> cxn = labrad.connect(host='localhost')

will create a connection to the labrad manager on localhost and
assign it to the variable 'cxn'.  Through this variable you can
find out about and talk to labrad servers.

To turn off tutorial mode, type:

>>> labrad.end_tutorial()
"""

def end_tutorial():
    global tutorial_mode
    tutorial_mode = False
    print """
Tutorial mode off.  Enjoy using labrad!
"""

