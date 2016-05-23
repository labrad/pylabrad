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

import functools
import inspect
import itertools
import types

import twisted.internet.defer as defer

from labrad import types as T, util

def _product(lists):
    """Return the cartesian product of a list of lists."""
    if not len(lists): return [[]]
    return [[h] + t for h in lists[0] for t in _product(lists[1:])]

def setting(lr_ID, lr_name=None, returns=[], unflatten=True, **params):
    """Decorator to turn a class method into a remotely accessible setting.

    This just creates a Setting class object which does the actual business.
    """
    def decorator(func):
        try:
            handler = Setting(func, lr_ID, lr_name, returns, unflatten, **params)
            func = handler.func  # might have gotten wrapped with inlineCallbacks
            func.ID = handler.ID
            func.name = handler.name
            func.accepts = handler.accepts
            func.returns = handler.returns
            func.handleRequest = handler.handleRequest
            func.getRegistrationInfo = handler.getRegistrationInfo
            return func
        except Exception:
            print 'Error in setting {} ({}):'.format(func.__name__, lr_ID)
            raise
    return decorator

class Setting(object):
    """Represents a single setting within a Server object.
    """
    def __init__(self, func, lr_ID, lr_name, returns, unflatten, **params):
        """Setting constructor
        Args:

            func (callable):   Function to implement the setting.
            lr_ID (int):       The ID number of the setting used in the labrad
                               protocol
            lr_name (str):     The setting name.  By default, this is derived
                               from the function name.
            returns:           The labrad type tag or list of tags the setting
                               returns
            unflatten (bool):  Request automatic unflattening of incoming data.
                               (default True)
            **params:          Additional keyword arguments indicate arguments
                               to the setting.  Each keyword should be a string
                               matching one of the formal parameters of func,
                               while the value is the type tag or list of tags
                               accepted by that parameter.

        If unflattening is requested, pylabrad will use the default unflattening
        for the data.  Otherwise, arguments will receive FlatData objects.  If
        there are multiple arguments, the top-level tuple will still be
        unpacked."""

        self.func = func
        self.ID = lr_ID
        self.name = lr_name or func.__name__
        self.returns = [returns] if isinstance(returns, basestring) else returns
        self.unflatten = unflatten
        self.description, self.notes = util.parseSettingDoc(func.__doc__)
        self.__doc__ = "Setting wrapper for {}\n\n{}".format(func.__name__, func.__doc__)
        
        ###
        # We need to validate the arguments.  Things we need to checks:
        #
        # 1) All parameters must match function arguments
        # 2) Function arguments with no specified parameter default to '?'
        # 3) The empty tag '' is only allowd on the first argument, and only
        #    if all other arguments are optional.
        # 4) If more than one argument are required, we expect to always receive
        #    a tuple and unpack it
        # 5) If only a single argument is allowed, we never unpack tuples
        # 6) If both =1 and >1 arguments are allowed, it is ambiguous whether to
        #    unpack tuples, so this case is not allowed:  The first argument
        #    cannot be a tuple or '?' tag if the second argument is optional.
        
        argspec = inspect.getargspec(self.func)
        args = argspec.args[2:] # Skip 'self' and context data arguments.

        if inspect.isgeneratorfunction(func):
            self.func = defer.inlineCallbacks(func)

        for arg in args:
            if arg not in params:
                params[arg] = ['?']

        for p in params.keys():
            if p not in args:
                raise ValueError("Setting parameter {} not accepted by function".format(p))
            if isinstance(params[p], basestring):
                params[p] = [params[p]]

        Nparams = len(args)
        Noptional = len(argspec.defaults) if argspec.defaults else 0
        Nrequired = Nparams - Noptional

        if Nrequired > 1:
            self.expand_cluster = "always"
        elif Nparams > 1:
            self.expand_cluster = "optional"
        else: # one or fewer arguments
            self.expand_cluster = "never"

        self.allow_none = Nrequired == 0

        if Nparams:
            for tag in params[args[0]]:
                tt = T.parseTypeTag(tag)
                if isinstance(tt, T.LRNone) and Nrequired > 1:
                    raise ValueError("First argument {} cannot accept '' "
                          "unless other arguments are optional".format(args[0]))
                if isinstance(tt, (T.LRAny, T.LRCluster)) and self.expand_cluster=="optional":
                    raise ValueError("First argument {} cannot accept type {} "
                          "because other arguments are optional".format(args[0], tt))
            for arg in args[1:]:
                for tag in params[arg]:
                    if isinstance(T.parseTypeTag(tag), T.LRNone):
                        raise ValueError("Argument {} cannot accept ''".format(arg))

        # Build list of accepted data types.
        # This is basically every combination of accepted types for each agrument,
        # including omitting any number of trailing optional arguments.

        accepted_types = []
        for i in range(Nrequired, Nparams+1):
            if i == 0:
                accepted_types.append('_')
            else:
                accept_tuples = itertools.product(*[params[arg] for arg in args[:i]])
                accepted_types.extend(combine_type_tags(x) for x in accept_tuples)
        self.accepts = accepted_types

    def handleRequest(self, server, c, flat_data):
        data_type = flat_data.tag

        if (self.expand_cluster == "always" or
            (self.expand_cluster == "optional"
             and isinstance(data_type, T.LRCluster))):
            if self.unflatten:
                data = flat_data.unflatten()
            else:
                data = flat_data.tag.partial_unflatten(flat_data.bytes,
                                                       flat_data.endianness)
            return self.func(server, c, *data)
        if self.allow_none and isinstance(data_type, T.LRNone):
            return self.func(server, c)

        if self.unflatten:
            data = flat_data.unflatten()
            return self.func(server, c, data)
        else:
            return self.func(server, c, flat_data)

    def getRegistrationInfo(self):
        return (self.ID, self.name, self.description,
                self.accepts, self.returns, self.notes)


def combine_type_tags(tags):
    """Combine one or more type tag strings into a single type tag.

    We cannot simply concatenate the tag strings because some of the input tags
    may have trailing comments.

    Args:
        tags (iterable[str]): The type tags to be combined into one type.

    Returns:
        (string): A tag representing a cluster of the given tags.
    """
    if len(tags) == 1:
        return tags[0]

    types = [T.parseTypeTag(tag) for tag in tags]
    return str(T.LRCluster(*types))


class MessageHandler(object):
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
        args, varargs, varkw, defaults = inspect.getargspec(f)
        args = args[lr_num_params:]

        # handle generators as defer.inlineCallbacks
        if inspect.isgeneratorfunction(f):
            f = defer.inlineCallbacks(f)

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

            @functools.wraps(f)
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

                @functools.wraps(f)
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
                for i, group in reversed(list(enumerate(groups))):
                    # if there are any LRNones in the group, we remove it
                    ts = [T.parseTypeTag(t) for t in group]
                    if T.LRNone() in ts:
                        groups.pop(i)

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

                @functools.wraps(f)
                def handleRequest(self, c, data):
                    if isinstance(data, tuple):
                        return f(self, c, *data)
                    elif data is None:
                        return f(self, c)
                    else:
                        return f(self, c, data)
            else:
                @functools.wraps(f)
                def handleRequest(self, c, data):
                    if isinstance(data, tuple):
                        return f(self, c, *data)
                    else:
                        return f(self, c, data)

        f.ID = lr_ID
        f.name = lr_name or f.__name__
        f.accepts = accepts_s
        f.returns = returns
        f.handleRequest = handleRequest

        # this is the data that will be sent to the manager to
        # register this setting to be remotely callable
        f.description, f.notes = util.parseSettingDoc(f.__doc__)
        def getRegistrationInfo():
            return (f.ID, f.name, f.description,
                    f.accepts, f.returns, f.notes)
        f.getRegistrationInfo = getRegistrationInfo

        return f
    return decorated
