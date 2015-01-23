# Copyright (C) 2008  Matthew Neeley
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

from twisted.internet.defer import inlineCallbacks, returnValue
from labrad.support import SafeIterDict

class RegistryWrapperAsync(SafeIterDict):

    """Wrapper around the labrad registry.

    The LabRAD registry can be used like a python class or a list.
    Registry entries are mapped to valid python identifiers by
    replacing all characters except letters and digits with '_', and by
    prefixing with '_' if the first letter is a digit.
    Python identifiers are mapped to registry entries by removing all '_'
    at the beginning or end and by replacing '_' in the middle with ' '.
    This means that not all registry entries can be accessed as attributes.
    For registry entries that are not valid python names you should use
    attributes e.g. mywrapper['Key Name'].
    """

    MESSAGE_ID = 463462

    @classmethod
    @inlineCallbacks
    def create(cls, cxn, directory=''):
        """Create a registry wrapper and initialize it."""
        wrapper = cls(cxn, directory)
        yield wrapper._init()
        returnValue(wrapper)

    def __init__(self, cxn, directory=''):
        """Basic (synchronous) initialization."""
        self._cxn = cxn
        self._ctx = cxn.context()
        if not isinstance(directory, list):
            directory = [directory]
        if directory[0] != '':
            directory = [''] + directory
        self._dir = directory
        self._listen(True)

    @inlineCallbacks
    def _init(self):
        """Initialize this registry wrapper.

        We get the data for this directory and create wrappers for
        all subdirectories.  We also sign up for change notifications.
        """
        p = self._packet()
        p.cd(self._dir, True)
        p.dir()
        ans = yield p.send()
        dirs, keys = ans['dir']
        _dict = SafeIterDict()
        for d in dirs:
            _dict[d] = self._wrapSubdir(d)
        p = self._packet()
        p.notify_on_change(self.MESSAGE_ID, True)
        for k in keys:
            p.get(k, key=k)
        ans = yield p.send()
        for d in dirs:
            _dict[d] = yield _dict[d]
        for k in keys:
            _dict[k] = ans[k]
        self.update(_dict)
        print 'done initing!'
        print 'data:', self

    def __del__(self):
        """Remove the listener when we are garbage collected."""
        self._listen(False)

    def _listen(self, listen):
        """Add or remove a listener for update messages."""
        #def print_(*args):
        #    print 'message:', args
        #    #print self._cxn._cxn.listeners
        #self._cxn._cxn.addListener(print_)
        if listen:
            func = self._cxn._cxn.addListener
        else:
            func = self._cxn._cxn.removeListener
        source = self._cxn.registry.ID # doesn't seem to work
        func(self._messageReceived, context=self._ctx, ID=self.MESSAGE_ID)

    def _wrapSubdir(self, dir):
        """Create a registry wrapper of a subdirectory."""
        return self.__class__.create(self._cxn, self._dir + [dir])

    def _getKey(self, key):
        """Get a key from this directory."""
        return self._cxn.registry.get(key, context=self._ctx)

    def _packet(self):
        """Create a packet to the registry."""
        return self._cxn.registry.packet(context=self._ctx)

    @inlineCallbacks
    def _messageReceived(self, c, data):
        """Handle update messages from the registry."""
        name, isDir, addOrChange = data
        print 'update message:', data
        try:
            if addOrChange:
                if isDir:
                    val = yield self._wrapSubdir(name)
                else:
                    val = yield self._getKey(name)
                self[name] = val
            else:
                del self[name]
            print 'done updating!'
            print 'data:', self
        except:
            print 'Error while updating Registry Wrapper for', self._dir
            from twisted.python.failure import Failure
            print Failure().getBriefTraceback()
