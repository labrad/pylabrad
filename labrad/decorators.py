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
labrad.decorators

Decorators that help in creating LabRAD servers.
"""

from __future__ import absolute_import

from functools import wraps
from inspect import getargspec

from twisted.internet.defer import inlineCallbacks
from zope.interface import implements

from labrad import types as T, util
from labrad.interfaces import IRequestHandler, IMessageHandler

def _isGenerator(f):
    """Check to see whether f is a generator.

    See the documentation on code objects at:
    http://docs.python.org/ref/types.html
    """
    return bool(f.func_code.co_flags & 0x20)

def _product(lists):
    """Return the cartesian product of a list of lists."""
    if not len(lists): return [[]]
    return [[h] + t for h in lists[0] for t in _product(lists[1:])]

class Setting(object):
    implements(IRequestHandler)
    
    def __init__(self, func):
        self.func = func
    
    def getRegistrationInfo(self):
        return (long(self.ID), self.name, self.description,
                self.accepts, self.returns, self.notes)
    
    def handleRequest(self, c, data):
        return self.func(c, data)

def setting(lr_ID, lr_name=None, returns=[], lr_num_params=2, **params):
    """Mark a server method as a remotely-accessible setting.

    The only required parameter is an integer ID.  You may
    also provide a name to override the name of the decorated
    function.  In addition, accepted types for each of the setting
    parameters may be provided as named parameters with a list of
    strings of allowed types.
    """
    def decorated(f):
        args, varargs, varkw, defaults = getargspec(f)
        args = args[lr_num_params:]

        # handle generators as inlineCallbacks
        if _isGenerator(f):
            f = inlineCallbacks(f)

        # make sure that defined params are actually accepted by the function.
        # having extra params would not affect the running, but it is
        # unnecessary and hence may indicate other problems with the code
        for p in params:
            if p not in args:
                raise Exception("'%s' is not a valid parameter." % p)
            # turn single string annotations into lists
            if isinstance(params[p], str):
                params[p] = [params[p]]

        Nparams = len(args)
        Noptional = 0 if defaults is None else len(defaults)
        Nrequired = Nparams - Noptional
        
        if Nparams == 0:
            accepts_s = [''] # only accept notifier
            accepts_t = [T.parseTypeTag(s) for s in accepts_s]

            @wraps(f)
            def handleRequest(self, c, data):
                return f(self, c)

        elif Nparams == 1:
            accepts_s = params.get(args[0], [])
            accepts_t = [T.parseTypeTag(s) for s in accepts_s]
            
            if Nrequired == 0:
                # if accepted types were specified, add '' to the list
                # we don't add '' if the list of accepted types is empty,
                # since this would make '' the ONLY accepted type
                if len(accepts_t) and T.LRNone() not in accepts_t:
                    accepts_s.append(': defaults [%s=%r]' \
                                     % (args[0], defaults[0]))
                    accepts_t.append(T.LRNone())
                
                @wraps(f)
                def handleRequest(self, c, data):
                    if data is None:
                        return f(self, c)
                    return f(self, c, data)

            else:
                # nothing special to do here
                handleRequest = f

        else:
            # sanity checks to make sure that we'll be able to
            # correctly dispatch to the function when called
            if Nrequired <= 1:
                if args[0] not in params:
                    raise Exception('Must specify types for first argument '
                                    'when fewer than two args are required.')
                for s in params[args[0]]:
                    t = T.parseTypeTag(s)
                    if isinstance(t, (T.LRAny, T.LRCluster)):
                        raise Exception('Cannot accept cluster or ? in first '
                                        'arg when fewer than two args are '
                                        'required.')
                                        
            # '' is not allowed on first arg when Nrequired > 1
            types = [T.parseTypeTag(s) for s in params.get(args[0], [])]
            if Nrequired > 1 and T.LRNone() in types:
                raise Exception("'' not allowed when more than "
                                "one arg is required.")

            # '' is never allowed on args after the first.
            for p in args[1:]:
                types = [T.parseTypeTag(s) for s in params.get(p, [])]
                if T.LRNone() in types:
                    raise Exception("'' not allowed after first arg.")

            # allowed types are as follows:
            # one type for each parameter, with the number of
            # parameters ranging from the total number down to
            # and including the required number
            # we don't include any zero-length group
            groups = []
            for n in range(Nparams, Nrequired-1, -1):
                lists = [params.get(a, ['?']) for a in args[:n]]
                if len(lists):
                    groups += _product(lists)

            accepts_t = []
            accepts_s = []
            for group in groups:
                if len(group) > 1:
                    t = T.LRCluster(*[T.parseTypeTag(t) for t in group])
                    s = ', '.join('%s{%s}' % (sub_t, arg)
                                  for sub_t, arg in zip(t, args))
                    s = '(%s)' % s
                else:
                    t = T.parseTypeTag(group[0])
                    if isinstance(t, T.LRCluster):
                        raise Exception("Can't accept cluster in first param.")
                    s = '%s{%s}' % (group[0], args[0])
                # add information about default values of unused params
                if len(group) < Nparams:
                    defstr = ', '.join('%s=%r' % (args[n], defaults[n-Nrequired])
                                       for n in range(len(group), Nparams))
                    s = s + ': defaults [%s]' % defstr
                accepts_t.append(t)
                accepts_s.append(s)

            if Nrequired == 0:
                if T.LRNone() not in accepts_t:
                    defstr = ', '.join('%s=%r' % (a, d)
                                       for a, d in zip(args, defaults))
                    accepts_s.append(': defaults [%s]' % defstr)
                    accepts_t.append(T.LRNone())
                
                @wraps(f)
                def handleRequest(self, c, data):
                    if isinstance(data, tuple):
                        return f(self, c, *data)
                    elif data is None:
                        return f(self, c)
                    else:
                        return f(self, c, data)
            else:
                @wraps(f)
                def handleRequest(self, c, data):
                    if isinstance(data, tuple):
                        return f(self, c, *data)
                    else:
                        return f(self, c, data)

        f.ID = lr_ID
        f.name = lr_name or f.__name__
        f.accepts = accepts_s
        f.returns = [returns] if isinstance(returns, str) else returns
        f.isSetting = True
        f.handleRequest = handleRequest
        
        # this is the data that will be sent to the manager to
        # register this setting to be remotely callable
        f.description, f.notes = util.parseSettingDoc(f.__doc__)
        def getRegistrationInfo():
            return (long(f.ID), f.name, f.description, 
                    f.accepts, f.returns, f.notes)
        f.getRegistrationInfo = getRegistrationInfo
        
        return f
    return decorated


class MessageHandler(object):
    implements(IMessageHandler)
    
    def __init__(self, func):
        self.func = func
    
    def handleMessage(self, c, data):
        return self.func(c, data)
    
    def handleNamedMessage(self, c, data):
        c.source, data = data
        return self.func(c, data)

def messageHandler(lr_ID, lr_name=None, returns=[], lr_num_params=2, **params):
    """Mark a server method as a remotely-accessible setting.

    The only required parameter is an integer ID.  You may
    also provide a name to override the name of the decorated
    function.  In addition, accepted types for each of the setting
    parameters may be provided as named parameters with a list of
    strings of allowed types.
    """
    def decorated(f):
        args, varargs, varkw, defaults = getargspec(f)
        args = args[lr_num_params:]

        # handle generators as inlineCallbacks
        if _isGenerator(f):
            f = inlineCallbacks(f)

        # make sure that defined params are actually accepted by the function.
        # having extra params would not affect the running, but it is
        # unnecessary and hence may indicate other problems with the code
        for p in params:
            if p not in args:
                raise Exception("'%s' is not a valid parameter." % p)
            # turn single string annotations into lists
            if isinstance(params[p], str):
                params[p] = [params[p]]

        Nparams = len(args)
        Noptional = 0 if defaults is None else len(defaults)
        Nrequired = Nparams - Noptional
        
        if Nparams == 0:
            accepts_s = [''] # only accept notifier
            accepts_t = [T.parseTypeTag(s) for s in accepts_s]

            @wraps(f)
            def handleRequest(self, c, data):
                return f(self, c)

        elif Nparams == 1:
            accepts_s = params.get(args[0], [])
            accepts_t = [T.parseTypeTag(s) for s in accepts_s]
            
            if Nrequired == 0:
                # if accepted types were specified, add '' to the list
                # we don't add '' if the list of accepted types is empty,
                # since this would make '' the ONLY accepted type
                if len(accepts_t) and T.LRNone() not in accepts_t:
                    accepts_s.append(': defaults [%s=%r]' \
                                     % (args[0], defaults[0]))
                    accepts_t.append(T.LRNone())
                
                @wraps(f)
                def handleRequest(self, c, data):
                    if data is None:
                        return f(self, c)
                    return f(self, c, data)

            else:
                # nothing special to do here
                handleRequest = f

        else:
            # sanity checks to make sure that we'll be able to
            # correctly dispatch to the function when called
            if Nrequired <= 1:
                if args[0] not in params:
                    raise Exception('Must specify types for first argument '
                                    'when fewer than two args are required.')
                for s in params[args[0]]:
                    t = T.parseTypeTag(s)
                    if isinstance(t, (T.LRAny, T.LRCluster)):
                        raise Exception('Cannot accept cluster or ? in first '
                                        'arg when fewer than two args are '
                                        'required.')
                                        
            # '' is not allowed on first arg when Nrequired > 1
            types = [T.parseTypeTag(s) for s in params.get(args[0], [])]
            if Nrequired > 1 and T.LRNone() in types:
                raise Exception("'' not allowed when more than "
                                "one arg is required.")

            # '' is never allowed on args after the first.
            for p in args[1:]:
                types = [T.parseTypeTag(s) for s in params.get(p, [])]
                if T.LRNone() in types:
                    raise Exception("'' not allowed after first arg.")

            # allowed types are as follows:
            # one type for each parameter, with the number of
            # parameters ranging from the total number down to
            # and including the required number
            # we don't include any zero-length group
            groups = []
            for n in range(Nparams, Nrequired-1, -1):
                lists = [params.get(a, ['?']) for a in args[:n]]
                if len(lists):
                    groups += _product(lists)

            accepts_t = []
            accepts_s = []
            for group in groups:
                if len(group) > 1:
                    t = T.LRCluster(*[T.parseTypeTag(t) for t in group])
                    s = ', '.join('%s{%s}' % (sub_t, arg)
                                  for sub_t, arg in zip(t, args))
                    s = '(%s)' % s
                else:
                    t = T.parseTypeTag(group[0])
                    if isinstance(t, T.LRCluster):
                        raise Exception("Can't accept cluster in first param.")
                    s = '%s{%s}' % (group[0], args[0])
                # add information about default values of unused params
                if len(group) < Nparams:
                    defstr = ', '.join('%s=%r' % (args[n], defaults[n-Nrequired])
                                       for n in range(len(group), Nparams))
                    s = s + ': defaults [%s]' % defstr
                accepts_t.append(t)
                accepts_s.append(s)

            if Nrequired == 0:
                if T.LRNone() not in accepts_t:
                    defstr = ', '.join('%s=%r' % (a, d)
                                       for a, d in zip(args, defaults))
                    accepts_s.append(': defaults [%s]' % defstr)
                    accepts_t.append(T.LRNone())
                
                @wraps(f)
                def handleRequest(self, c, data):
                    if isinstance(data, tuple):
                        return f(self, c, *data)
                    elif data is None:
                        return f(self, c)
                    else:
                        return f(self, c, data)
            else:
                @wraps(f)
                def handleRequest(self, c, data):
                    if isinstance(data, tuple):
                        return f(self, c, *data)
                    else:
                        return f(self, c, data)

        f.ID = lr_ID
        f.name = lr_name or f.__name__
        f.accepts = accepts_s
        f.returns = returns
        f.isSetting = True
        f.handleRequest = handleRequest
        
        # this is the data that will be sent to the manager to
        # register this setting to be remotely callable
        f.description, f.notes = util.parseSettingDoc(f.__doc__)
        def getRegistrationInfo():
            return (long(f.ID), f.name, f.description, 
                    f.accepts, f.returns, f.notes)
        f.getRegistrationInfo = getRegistrationInfo
        
        return f
    return decorated
