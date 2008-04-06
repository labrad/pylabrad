import os
import simplejson
import labrad
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.web import resource, static, server

print simplejson.dumps(['a', 'b', u'c'])
print simplejson.dumps((1,2))
HERE_DIR = os.path.split(os.path.abspath(__file__))[0]
JSON = lambda stuff: static.Data(simplejson.dumps(stuff), type='application/json')

def _nodes(cxn):
    servers = sorted(cxn.servers.keys())
    return [s for s in servers if s.startswith('node')]

class JSONResource(resource.Resource):
    def __init__(self, func, *a, **kw):
        self.func = func
        self.a = a
        self.kw = kw
        
    def render(self, request):
        @inlineCallbacks
        def doRequest():
            try:
                cxn = yield labrad.connectAsync()
                func = getattr(self, 'remote_' + path)
                resp = yield self.func(cxn, request, *self.a, **self.kw)
                result = simplejson.dumps({u'result': resp})
            except Exception, e:
                result = simplejson.dumps({u'error': unicode(e)})
            request.setHeader('content-type', 'application/json')
            request.setHeader('content-length', result)
            if request.method != 'HEAD':
                request.write(result)
            request.finish()
        doRequest()
        return server.NOT_DONE_YET
            
    
class NodeAPI(resource.Resource):
    def getChild(self, path, request):
        func = getattr(self, 'remote_' + path)
        return JSONResource(func)
        
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
                        row.append([unicode(instance), False])
            status.append(row)
        
        returnValue([servers, nodes, status])
    
    def remote_start(self, cxn, request):
        node = request.arg('node')
        server = request.arg('server')
        return cxn[node].start(server)
        
    def remote_restart(self, cxn, request):
        node = request.arg('node')
        server = request.arg('server')
        return cxn[node].restart(server)
        
    def remote_stop(self, cxn, request):
        node = request.arg('node')
        server = request.arg('server')
        return cxn[node].stop(server)

if __name__ == '__main__':
    from twisted.internet import reactor
    root = static.File(os.path.join(HERE_DIR, 'www', 'org.labrad.NodeController'))
    root.indexNames = ['NodeController.html']
    root.putChild('api', NodeAPI())
    site = server.Site(root)
    reactor.listenTCP(7667, site)
    reactor.run()