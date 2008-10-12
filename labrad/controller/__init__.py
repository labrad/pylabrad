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

import os
import hashlib
import random

import labrad
from labrad.config import ConfigFile
from labrad.util import maybeTimeout, simplejson
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
                 hasattr(cxn[s], 'restart') and \
                 hasattr(cxn[s], 'status')]

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
    
class JSONTransport(resource.Resource):
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
        self.timeoutCall.reset(self.timeoutDelay)
    
    def _timeout(self):
        del transports[self.ID]
    
    def lookupMethod(self, name):
        return getattr(self, 'remote_' + name)
    
    def invokeMethod(self, id, name, *args, **kw):
        """Called when the client invokes a method on the server."""
        self.resetTimeout()
        func = self.lookupMethod(name)
        d = defer.maybeDeferred(func, *args, **kw)
        d.addCallback(self._addResult, id)
        d.addErrback(self._addError, id)
    
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
    
    def _addResult(self, result, id):
        self._addResponse(id=id, result=result)
    
    def _addError(self, failure, id):
        self._addResponse(id=id, error=failure.getBriefTraceback())
    
    def _addResponse(self, **kw):
        self.responses.append(kw)
        self._finishWaiter()
    
    def _finishWaiter(self):
        if self.waiter:
            d = self.waiter
            self.waiter = None
            reactor.callLater(0, d.callback, self._flushResponses())
            
    def _cancelTimeout(self, result, timeoutCall):
        if timeoutCall.active():
            timeoutCall.cancel()
        return result
    
    def _flushResponses(self):
        resp = simplejson.dumps(self.responses)
        self.responses = []
        return resp
        
class NodeProxy(JSONTransport):
    def __init__(self, cxn, ID):
        JSONTransport.__init__(self, ID)
        self.cxn = cxn
    
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
        return self.cxn.servers.keys()
        
    def remote_list_nodes(self):
        return _nodes(self.cxn)
    
    @inlineCallbacks
    def remote_status(self):
        cxn = self.cxn
        servers = yield self.remote_available_servers()
        nodes = yield self.remote_list_nodes()
        yield DeferredList([cxn[node].refresh_servers() for node in nodes], fireOnOneErrback=True)
        
        status_dict = {}
        info = yield DeferredList([cxn[node].status() for node in nodes])
        for (success, result), node in zip(info, _nodes(cxn)):
            if success:
                status_dict[node] = result
        
        status = []
        for server in servers:
            row = []
            for node in nodes:
                if node not in status_dict:
                    row.append([False, '', 'unavailable', server, [], []])
                else:
                    found = False
                    for name, desc, ver, inst, vars, instances in status_dict[node]:
                        if name == server:
                            row.append([True, desc, 'Version: ' + ver, inst, vars, instances])
                            found = True
                            break
                    if not found:
                        row.append([False, '', 'unavailable', server, [], []])
            status.append(row)
        returnValue([servers, nodes, status])
    
    @inlineCallbacks
    def remote_refresh_servers(self, node):
        yield self.cxn[node].refresh_servers(context=self.cxn.context())
        returnValue('%s refreshed' % node)
    
    def remote_start(self, node, server):
        return self.cxn[node].start(str(server), context=self.cxn.context())
        
    def remote_restart(self, node, server):
        return self.cxn[node].restart(str(server), context=self.cxn.context())
        
    def remote_stop(self, node, server):
        return self.cxn[node].stop(str(server), context=self.cxn.context())
    
    @inlineCallbacks
    def remote_iplist(self):
        p = self.cxn.manager.packet()
        p.whitelist()
        p.blacklist()
        resp = yield p.send()
        ips = sorted([(addr, True) for addr in resp.whitelist] + \
                     [(addr, False) for addr in resp.blacklist])
        returnValue(ips)
    
    def remote_blacklist(self, address):
        return self.cxn.manager.blacklist(str(address))
    
    def remote_whitelist(self, address):
        return self.cxn.manager.whitelist(str(address))

transports = {}
    
class NodeAPI(resource.Resource):
    reconnectDelay = 10
    
    def _connect(self):
        d = connectAsync(self.host, self.port, name='Web Interface Client')
        d.addCallbacks(self._connectionSucceeded, self._connectionFailed)

    def sendMessage(self, message, **kw):
        for t in transports.values():
            t.sendMessage(message, **kw)

    @inlineCallbacks
    def _connectionSucceeded(self, cxn):
        try:
            cxn.onDisconnect().addBoth(self._connectionFailed)
            self.cxn = cxn
            self.connected = True
            print 'Connected to manager %s:%d.' % (self.host, self.port)
            
            # sign up for named messages
            def relay(c, data, message):
                source, payload = data
                kw = dict(payload)
                self.sendMessage(message, **kw)
            messages = ['node.server_starting', 'node.server_started',
                        'node.server_stopping', 'node.server_stopped',
                        'node.status']
            p = cxn.manager.packet()
            for ID, message in enumerate(messages):
                cxn.manager.addListener(relay, ID=ID+1234, kw=dict(message=message))
                p.subscribe_to_named_message(message, ID+1234, True)
            yield p.send()
                
            # sign up for server connect/disconnect messages
            self._serverNames = dict((yield cxn.manager.servers()))
            
            def serverConnected(c, data):
                ID, name = data
                self.sendMessage('Server Connected', name=name)
            cxn.manager.addListener(serverConnected, ID=12345678)
            yield cxn.manager.subscribe_to_named_message('Server Connect', 12345678, True)
            
            def serverDisconnected(c, data):
                ID, name = data
                self.sendMessage('Server Disconnected', name=name)
            cxn.manager.addListener(serverDisconnected, ID=12345679)
            yield cxn.manager.subscribe_to_named_message('Server Disconnect', 12345679, True)
            
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
            status = self.channel.site.users[user]
            #if self.path == '/__logout__':
            #    status['logged_in'] = False
            #    return False
            pw = status['pw']
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

def generateNonce():
    return ''.join(random.choice('0123456789abcdef') for _ in range(32))
        
def makeNodeControllerSite(host, port):
    try:
        passFile = ConfigFile('controller.ini')
    except:
        passFile = ConfigFile('controller-template.ini')

    root = static.File(WEB_DIR)
    root.indexNames = ['NodeController.html']
    api = NodeAPI()
    api.host = host
    api.port = port
    api._connect()
    root.putChild('api', api)
    site = server.Site(root)
    site.requestFactory = DigestAuthRequest
        
    site.users = {}
    for section in passFile.sections():
        try:
            user = passFile.get(section, 'username')
            pw = passFile.get(section, 'password')
            site.users[user] = {'pw': pw, 'logged_in': True}
        except Exception, e:
            print e
    return site

if __name__ == '__main__':
    from twisted.internet import reactor
    site = makeNodeControllerSite('localhost', 7682)
    reactor.listenTCP(7667, site)
    reactor.run()