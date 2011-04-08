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

from __future__ import with_statement

import os
import sys

menuDir = "LabRAD"
menuPath = os.path.join(get_special_folder_path("CSIDL_COMMON_PROGRAMS"),
                        menuDir)
scriptsPath = os.path.join(sys.prefix, 'Scripts')
twistdPath = os.path.join(scriptsPath, 'twistd.py')
ipyPath = os.path.join(scriptsPath, 'ipython.py')
libPath = os.path.join(sys.prefix, 'Lib', 'site-packages', 'labrad')
configPath = os.path.join(sys.prefix, 'Lib', 'site-packages', 'labrad', 'config')

def mkdir(a, *p):
    """Make a directory and tell the installer."""
    path = os.path.join(a, *p)
    if not os.path.isdir(path):
        os.mkdir(path)
        directory_created(path)

def rmdir(a, *p):
    path = os.path.join(a, *p)
    os.rmdir(path)
    
def install():
    print "Creating start menu entries..."
    mkdir(menuPath)

    print "Removing old node.py* files...",
    for suffix in ['', 'c', 'o']:
        nodeDotPy = os.path.join(libPath, "node.py" + suffix)
        if os.path.isfile(nodeDotPy):
            os.remove(nodeDotPy)
    print "done."

    print "Creating node shortcut...",
    nodeShortcut = os.path.join(menuPath, "LabRAD Node.lnk")
    if os.path.isfile(nodeShortcut):
        os.remove(nodeShortcut)
    create_shortcut(twistdPath, "Node to start and stop LabRAD servers",
	            nodeShortcut, "-n labradnode")
    file_created(nodeShortcut)
    print "done."

    if os.path.exists(ipyPath):
        print "Creating LabRAD shell shortcut...",
        ipyShortcut = os.path.join(menuPath, "LabRAD Shell.lnk")
        ipyScript = os.path.join(configPath, "ipythonrc-labrad.ini")
        if os.path.isfile(ipyShortcut):
            os.remove(ipyShortcut)
        create_shortcut(ipyPath, "",
                        ipyShortcut, "-rcfile %s" % ipyScript)
        file_created(ipyShortcut)
        print "done."

        print "Creating LabRAD tutorial shortcut...",
        ipyShortcut = os.path.join(menuPath, "LabRAD Tutorial.lnk")
        ipyScript = os.path.join(configPath, "ipythonrc-labrad_tut.ini")
        if os.path.isfile(ipyShortcut):
            os.remove(ipyShortcut)
        create_shortcut(ipyPath, "",
                        ipyShortcut, "-rcfile %s" % ipyScript)
        file_created(ipyShortcut)
        print "done."
    else:
        print "IPython not found.  Skipping shortcuts for IPython shell."


def remove():
    pass


if __name__ == '__main__':
    if sys.argv[1] == '-install':
        install()
    elif sys.argv[1] == '-remove':
        remove()
    else:
        raise Exception('Unknown options: %s.' % sys.argv)
