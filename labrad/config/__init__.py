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

from ConfigParser import SafeConfigParser

# by default, we look for configuration files
# here in the labrad.config directory
configPath = os.path.split(__file__)[0]

class ConfigFile(object):
    """Wrapper for configuration files."""
    
    def __init__(self, name, path=configPath):
        if not name.endswith('.ini'):
            name += '.ini'
        self.name = name
        self.fname = os.path.join(path, name)
        self.parser = SafeConfigParser()
        with open(self.fname) as f:
            self.parser.readfp(f)
        
    def save(self):
        with open(self.fname, 'w') as f:
            self.parser.write(f)
        
    def __getattr__(self, key):
        """Delegate everything else to the config parser."""
        return getattr(self.parser, key)
