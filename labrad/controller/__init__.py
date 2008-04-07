import os
import hashlib

import labrad
from labrad.config import ConfigFile
from labrad.util import simplejson

from labrad.wrappers import AsyncClient
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.python.failure import Failure
from twisted.web import http, resource, static, server

HERE_DIR = os.path.split(os.path.abspath(__file__))[0]
WEB_DIR = os.path.join(HERE_DIR, 'www', 'org.labrad.NodeController')
#WEB_DIR = 'U:/projects/NodeController/www/org.labrad.NodeController'
JSON = lambda stuff: static.Data(simplejson.dumps(stuff), type='application/json')

def _nodes(cxn):
    servers = sorted(cxn.servers.keys())
    return [s for s in servers if s.startswith('node')]

class JSONResource(resource.Resource):
    def __init__(self, cxn, func, *a, **kw):
        self.cxn = cxn
        self.func = func
        self.a = a
        self.kw = kw
        
    def render(self, request):
        @inlineCallbacks
        def doRequest():
            try:
                resp = yield self.func(self.cxn, request, *self.a, **self.kw)
                result = simplejson.dumps({u'result': resp})
            except Exception, e:
                f = Failure(e)
                msg = f.getTraceback(elideFrameworkCode=1, detail='verbose')
                result = simplejson.dumps({u'error': unicode(msg)})
            request.setHeader('content-type', 'application/json')
            request.setHeader('content-length', len(result))
            if request.method != 'HEAD':
                request.write(result)
            request.finish()
        doRequest()
        return server.NOT_DONE_YET
            
    
class NodeAPI(resource.Resource):
    def getChild(self, path, request):
        func = getattr(self, 'remote_' + path)
        return JSONResource(self.cxn, func)
        
    @inlineCallbacks
    def remote_available_servers(self, cxn, request):
        resp = yield DeferredList([cxn[node].available_servers() for node in _nodes(cxn)])
        avail = set()
        for success, result in resp:
            if success:
                avail.update(result)
        returnValue(sorted(unicode(name) for name in avail))
        
    def remote_list_servers(self, cxn, request):
        return [unicode(s) for s in cxn.servers.keys()]
        
    def remote_list_nodes(self, cxn, request):
        return [unicode(s) for s in _nodes(cxn)]
        
    @inlineCallbacks
    def remote_list_both(self, cxn, request):
        servers = yield self.remote_available_servers(cxn, request)
        nodes = yield self.remote_list_nodes(cxn, request)
        
        status_dict = {}
        running = yield DeferredList([cxn[node].running_servers() for node in _nodes(cxn)])
        for (success, result), node in zip(running, _nodes(cxn)):
            if success:
                status_dict[node] = result
         
        status = []
        for server in servers:
            row = []
            for node in nodes:
                if node not in status_dict:
                    row.append([unicode(server), False])
                else:
                    found = False
                    for running_server, instance in status_dict[node]:
                        if running_server == server:
                            row.append([unicode(instance), True])
                            found = True
                            break
                    if not found:
                        row.append([unicode(server), False])
            status.append(row)
        
        returnValue([servers, nodes, status])
    
    @inlineCallbacks
    def remote_iplists(self, cxn, request):
        p = cxn.manager.packet()
        p.whitelist()
        p.blacklist()
        resp = yield p.send()
        returnValue((sorted(resp.whitelist), sorted(resp.blacklist)))
    
    def remote_blacklist(self, cxn, request):
        address = request.args['address'][0]
        return cxn.manager.blacklist(address)
    
    def remote_whitelist(self, cxn, request):
        address = request.args['address'][0]
        return cxn.manager.whitelist(address)
    
    def remote_start(self, cxn, request):
        node = request.args['node'][0]
        server = request.args['server'][0]
        return cxn[node].start(server)
        
    def remote_restart(self, cxn, request):
        node = request.args['node'][0]
        server = request.args['server'][0]
        return cxn[node].restart(server)
        
    def remote_stop(self, cxn, request):
        node = request.args['node'][0]
        server = request.args['server'][0]
        return cxn[node].stop(server)

class DigestAuthRequest(server.Request):
    def process(self):
        "Process a request."
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
            if self.path == '/__logout__':
                status['logged_in'] = False
                return False
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
        self.setHeader('content-type', "text/html")

        self.setHeader('WWW-Authenticate', """Digest realm="LabRAD Controller", qop="auth", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", opaque="5ccc069c403ebaf9f0171e9517f40e41" """)
        self.write('<html><h1>Invalid username/password!</h1></html>')
        self.finish()
        
def makeNodeControllerSite(host, port):
    root = static.File(WEB_DIR)
    root.indexNames = ['NodeController.html']
    api = NodeAPI()
    api.cxn = AsyncClient('Node Controller')
    api.cxn.connect(host, port)
    root.putChild('api', api)
    site = server.Site(root)
    site.requestFactory = DigestAuthRequest

    try:
        passFile = ConfigFile('controller.ini')
    except:
        passFile = ConfigFile('controller-template.ini')
        
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
    root = static.File(WEB_DIR)
    root.indexNames = ['NodeController.html']
    api = NodeAPI()
    api.cxn = AsyncClient('Node Controller')
    api.cxn.connect('localhost', 7682)
    root.putChild('api', api)
    site = server.Site(root)
    site.requestFactory = DigestAuthRequest

    try:
        passFile = ConfigFile('controller.ini')
    except:
        passFile = ConfigFile('controller-template.ini')
        
    site.users = {}
    for section in passFile.sections():
        try:
            user = passFile.get(section, 'username')
            pw = passFile.get(section, 'password')
            site.users[user] = {'pw': pw, 'logged_in': True}
        except Exception, e:
            print e
    
    reactor.listenTCP(7667, site)
    reactor.run()