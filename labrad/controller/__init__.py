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
import hashlib
import random
from contextlib import contextmanager

import labrad
from labrad.util import simplejson
from labrad.wrappers import connectAsync

from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.python.failure import Failure
from twisted.web import http, resource, static, server

HERE_DIR = os.path.split(os.path.abspath(__file__))[0]
WEB_DIR = os.path.join(HERE_DIR, 'gwt', 'www', 'org.labrad.NodeController')

def _nodes(cxn):
    servers = sorted(cxn.servers.keys())
    return [s for s in servers
              if s.lower().startswith('node') and \
                 hasattr(cxn[s], 'start') and \
                 hasattr(cxn[s], 'stop') and \
                 hasattr(cxn[s], 'restart')]

class JSONResource(resource.Resource):
    def __init__(self, cxn, func, *a, **kw):
        self.cxn = cxn
        self.func = func
        self.a = a
        self.kw = kw
        
    def render(self, request):
        d = defer.maybeDeferred(self.func, self.cxn, request, *self.a, **self.kw)
        d.addCallback(self._dumpResult)
        d.addErrback(self._dumpError)
        d.addBoth(self._finishRequest, request)
        return server.NOT_DONE_YET
    
    def _dumpResult(self, result):
        return simplejson.dumps({'result': result})
    
    def _dumpError(self, failure):
        msg = failure.getTraceback(elideFrameworkCode=1, detail='verbose')
        return simplejson.dumps({'error': unicode(msg)})
    
    def _finishRequest(self, result, request):
        request.setHeader('content-type', 'application/json')
        request.setHeader('content-length', len(result))
        if request.method != 'HEAD':
            request.write(result)
        request.finish()
            
    
class PushHandler(resource.Resource):
    """Handle messages that have been pushed to us."""
    def __init__(self, transport):
        self.transport = transport
        
    def render(self, request):
        try:
            content = request.content.read()
            data = simplejson.loads(content)
            self.transport.invokeMethod(data['id'], data['method'],
                                        *data['args'], **data['kw'])
            return ''
        except Exception, e:
            return simplejson.dumps({'error': str(e)})
    
    
class PullHandler(resource.Resource):
    """Collect responses and send them when pulled."""
    def __init__(self, transport):
        self.transport = transport
        
    def render(self, request):
        d = self.transport.getResponses()
        d.addCallback(self._push, request)
        return server.NOT_DONE_YET
        
    def _push(self, result, request):
        request.setHeader('content-type', 'application/json')
        request.setHeader('content-length', len(result))
        request.write(result)
        request.finish()

transports = {}
    
class JSONTransport(resource.Resource):
    """Provides remote method invocation and messaging over http."""
    
    timeoutDelay = 100 # time to wait before killing this transport
    pullDelay = 10 # maximum length of time to keep a pull request open
    
    def __init__(self, ID):
        self.children = {}
        self.putChild('push', PushHandler(self))
        self.putChild('pull', PullHandler(self))
        self.responses = []
        self.waiter = None
        self.timeoutCall = reactor.callLater(self.timeoutDelay, self._timeout)
        self.ID = ID
    
    def resetTimeout(self):
        """Reset the timing out of this transport."""
        self.timeoutCall.reset(self.timeoutDelay)
    
    def _timeout(self):
        """Timeout this transport by deleting it from the transport dict."""
        del transports[self.ID]
    
    def lookupMethod(self, name):
        """Lookup a method to be invoked by name."""
        return getattr(self, 'remote_' + name)
    
    @inlineCallbacks
    def invokeMethod(self, id, name, *args, **kw):
        """Called when the client invokes a method on the server."""
        self.resetTimeout()
        try:
            func = self.lookupMethod(name)
            result = yield func(*args, **kw)
            self._addResponse(id=id, result=result)
        except:
            self._addResponse(id=id, error=Failure().getBriefTraceback())
    
    def getResponses(self):
        """Called by the client to get all pending responses.
        
        If no responses are waiting, return a deferred that will be
        fired later when responses become available.
        """
        self.resetTimeout()
        d = defer.Deferred()
        if len(self.responses):
            reactor.callLater(0, d.callback, self._flushResponses())
        else:
            self.waiter = d
            timeoutCall = reactor.callLater(self.pullDelay, self._finishWaiter)
            d.addBoth(self._cancelTimeout, timeoutCall)
        return d
    
    def sendMessage(self, msg, *args, **kw):
        """Called by the server to push messages out to the client."""
        self._addResponse(message=msg, args=args, kw=kw)
            
    def _addResponse(self, **kw):
        """Add to the current response list and send it if waiting."""
        self.responses.append(kw)
        self._finishWaiter()
    
    def _finishWaiter(self):
        """Finish sending responses out to a waiting request."""
        if self.waiter:
            d = self.waiter
            self.waiter = None
            reactor.callLater(0, d.callback, self._flushResponses())
            
    def _cancelTimeout(self, result, timeoutCall):
        """Cancel a timeout call, passing the deferred result through."""
        if timeoutCall.active():
            timeoutCall.cancel()
        return result
    
    def _flushResponses(self):
        """Serialize the current list of response and clear the list."""
        resp = simplejson.dumps(self.responses)
        self.responses = []
        return resp
    
        
class NodeProxy(JSONTransport):
    def __init__(self, cxn, ID):
        JSONTransport.__init__(self, ID)
        self.contextPool = set()
        self.cxn = cxn
    
    @contextmanager
    def context(self):
        """Create a new context or reuse one from the pool."""
        if len(self.contextPool):
            ctx = self.contextPool.pop()
        else:
            ctx = self.cxn.context()
        try:
            yield ctx
        finally:
            self.contextPool.add(ctx)
    
    @inlineCallbacks
    def remote_available_servers(self):
        cxn = self.cxn
        resp = yield DeferredList([cxn[node].available_servers() for node in _nodes(cxn)])
        avail = set()
        for success, result in resp:
            if success:
                avail.update(result)
        returnValue(sorted(avail))
        
    def remote_list_servers(self):
        """Get a list of connected LabRAD server."""
        return self.cxn.servers.keys()
        
    def remote_list_nodes(self):
        """Get a list of connected nodes."""
        return _nodes(self.cxn)
    
    @inlineCallbacks
    def remote_status(self):
        """Get the status of all nodes."""
        cxn = self.cxn
        nodes = _nodes(cxn)
        
        requests = [cxn[node].status() for node in nodes]
        status_dict = {}
        for node, request in zip(nodes, requests):
            try:
                status_dict[node] = yield request
            except:
                print "Error while getting status of node:", node
        returnValue(status_dict)
    
    @inlineCallbacks
    def remote_refresh_servers(self, node):
        """Trigger a node to refresh its server list."""
        with self.context() as ctx:
            yield self.cxn[node].refresh_servers(context=ctx)
        returnValue('%s refreshed' % node)
    
    @inlineCallbacks
    def remote_start(self, node, server):
        """Start a server on the given node."""
        with self.context() as ctx:
            inst = yield self.cxn[node].start(str(server), context=ctx)
        returnValue(inst)
        
    @inlineCallbacks
    def remote_restart(self, node, server):
        """Restart a server on the given node."""
        with self.context() as ctx:
            inst = yield self.cxn[node].restart(str(server), context=ctx)
        returnValue(inst)
        
    @inlineCallbacks
    def remote_stop(self, node, server):
        """Stop a server on the given node."""
        print "stop called:", node, server
        with self.context() as ctx:
            inst = yield self.cxn[node].stop(str(server), context=ctx)
        returnValue(inst)
    
    @inlineCallbacks
    def remote_iplist(self):
        """Get a list of (str, bool) tuples of allowed/disallowed addresses."""
        p = self.cxn.manager.packet()
        p.whitelist()
        p.blacklist()
        resp = yield p.send()
        ips = sorted([(addr, True) for addr in resp.whitelist] + \
                     [(addr, False) for addr in resp.blacklist])
        returnValue(ips)
        
    def remote_blacklist(self, addr):
        """Add an address to the blacklist."""
        return self.cxn.manager.blacklist(str(addr))
    
    def remote_whitelist(self, addr):
        """Add an address to the whitelist."""
        return self.cxn.manager.whitelist(str(addr))


class ControllerConfig(object):
    """Load configuration from the registry and monitor it for changes."""
        
    @classmethod
    @inlineCallbacks
    def create(cls, parent):
        """Loads controller configuration from the registry."""
        instance = cls(parent)
        yield instance._init()
        returnValue(instance)
    
    def __init__(self, parent):
        self.parent = parent
        cxn = parent.cxn
        self._cxn = cxn
        self._reg = cxn.registry
        self._ctx = cxn.context()
        
    @inlineCallbacks
    def _init(self):
        """Load from registry and start monitoring for changes."""
        p = self._packet()
        p.cd(['', 'Nodes', '__controller__'], True)
        yield p.send()
        yield self._load()
        # setup messages when registry changes
        self._reg.addListener(self._handleMessage, context=self._ctx)
        p = self._packet()
        p.notify_on_change(2345, True)
        yield p.send()
    
    def _packet(self):
        """Create a packet to the registry server in our context."""
        return self._reg.packet(context=self._ctx)
            
    @inlineCallbacks
    def _load(self):
        """Load the current configuration out of the registry."""
        pw = generateNonce(8) # generate a random password
        p = self._packet()
        p.get('users', '*(ss)', True, [('webuser', pw)], key='users')
        ans = yield p.send()
        self.users = dict(ans.users)
        returnValue(ans.users)
        
    def _handleMessage(self, c, msg):
        """Reload when we get a message from the registry."""
        return self._load()
        
    
class NodeAPI(resource.Resource):
    reconnectDelay = 10
    
    def _connect(self):
        d = connectAsync(self.host, self.port, name='Web Interface Client')
        d.addCallbacks(self._connectionSucceeded, self._connectionFailed)

    def sendMessage(self, message, **kw):
        """Forward a message to all connected transports."""
        for t in transports.values():
            t.sendMessage(message, **kw)

    @inlineCallbacks
    def _connectionSucceeded(self, cxn):
        try:
            cxn.onDisconnect().addBoth(self._connectionFailed)
            self.cxn = cxn
            self.connected = True
            print 'Connected to manager %s:%d.' % (self.host, self.port)
            
            # lookup password information in the registry
            self.config = yield ControllerConfig.create(self)
            
            p = cxn.manager.packet()
            
            # sign up for named messages
            def relay(c, data, message):
                source, payload = data
                kw = dict(payload)
                self.sendMessage(message, **kw)
            messages = ['node.server_starting', 'node.server_started',
                        'node.server_stopping', 'node.server_stopped',
                        'node.status']
            for ID, message in enumerate(messages):
                cxn.manager.addListener(relay, ID=ID+1234, kw=dict(message=message))
                p.subscribe_to_named_message(message, ID+1234, True)
            
            # sign up for server connect/disconnect messages
            def serverConnected(c, data):
                ID, name = data
                self.sendMessage('Server Connected', name=name)
            cxn.manager.addListener(serverConnected, ID=12345678)
            p.subscribe_to_named_message('Server Connect', 12345678, True)
            
            def serverDisconnected(c, data):
                ID, name = data
                self.sendMessage('Server Disconnected', name=name)
            cxn.manager.addListener(serverDisconnected, ID=12345679)
            p.subscribe_to_named_message('Server Disconnect', 12345679, True)
            
            # finish signup
            yield p.send()
            
        except Exception, e:
            print e
            print 'Something went wrong in connection.'
            self._reconnect()

    def _connectionFailed(self, reason):
        print reason.getErrorMessage()
        self._reconnect()
        
    def _reconnect(self):
        self.cxn = None
        print 'Will try to reconnect in %d seconds...' % self.reconnectDelay
        reactor.callLater(self.reconnectDelay, self._connect)
    
    def getChild(self, path, request):
        if path == 'transport':
            ID = request.args['ID'][0]
            t = transports[ID]
            t.cxn = self.cxn
            return t
        func = getattr(self, 'remote_' + path)
        return JSONResource(self.cxn, func)
        
    def remote_get_transport_ID(self, cxn, request):
        while 1:
            ID = generateNonce()
            if ID not in transports:
                break
        transports[ID] = NodeProxy(self.cxn, ID)
        return ID

class DigestAuthRequest(server.Request):
    def process(self):
        """Process a request."""
        if self.checkAuthorization():
            server.Request.process(self)
        else:
            self.sendUnauthorizedResponse()
        
    def checkAuthorization(self):
        auth = self.getHeader('Authorization')
        if auth is None:
            return False
        auth = auth.strip()
        if not auth.startswith('Digest'):
            return False
        try:
            auth = [s.split('=', 1) for s in auth[6:].split(',')]
            auth = dict([s.strip().strip('"') for s in item] for item in auth)
            
            def hash(*strs):
                m = hashlib.md5()
                m.update(':'.join(strs))
                return m.hexdigest()
    
            user = auth['username']
            pw = self.channel.site.getPassword(user)
            ha1 = hash(user, auth['realm'], pw)
            ha2 = hash(self.method, auth['uri'])
            response = hash(ha1, auth['nonce'], auth['nc'],
                            auth['cnonce'], auth['qop'], ha2)
            
            return response == auth['response']
        except Exception, e:
            print e
        return False
        
    def sendUnauthorizedResponse(self):
        self.setResponseCode(http.UNAUTHORIZED)

        # set various default headers
        self.setHeader('server', server.version)
        self.setHeader('date', http.datetimeToString())
        self.setHeader('content-type', 'text/html')

        realm = 'LabRAD Controller'
        nonce = generateNonce()
        opaque = generateNonce()
        msg = 'Digest realm="%s", qop="auth", nonce="%s", opaque="%s"'
        self.setHeader('WWW-Authenticate', msg % (realm, nonce, opaque))
        self.write('<html><h1>Invalid username/password!</h1></html>')
        self.finish()

def generateNonce(length=32):
    return ''.join(random.choice('0123456789abcdef') for _ in range(length))
        
def makeNodeControllerSite(host, port):
    """Create a new node controller site.
    
    This site serves up a directory 
    """
    api = NodeAPI()
    api.host = host
    api.port = port
    api._connect()
    def getPassword(user):
        return api.config.users[user]
    root = static.File(WEB_DIR)
    root.indexNames = ['NodeController.html']
    root.putChild('api', api)
    site = server.Site(root)
    site.requestFactory = DigestAuthRequest
    site.getPassword = getPassword
    return site

if __name__ == '__main__':
    from twisted.internet import reactor
    from labrad import constants as C
    site = makeNodeControllerSite(C.MANAGER_HOST, C.MANAGER_PORT)
    reactor.listenTCP(C.HTTP_PORT, site)
    reactor.run()