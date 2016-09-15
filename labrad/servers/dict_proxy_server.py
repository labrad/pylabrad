from labrad import util
from labrad.server import LabradServer, setting

from twisted.internet.defer import returnValue

class DictProxyServer(LabradServer):
    name = "dict_proxy_server"

    @setting(11, server='s', key='s')
    def get_in_this_context(self, c, server, key):
        "Get from the specified server in this context"
        result = yield self.client[server].get(key, context=c.ID)
        returnValue(result)

    @setting(12, server='s', context='(ww)', key='s')
    def get_in_other_context(self, c, server, context, key):
        "Get from the specified server in the specified context"
        result = yield self.client[server].get(key, context=context)
        returnValue(result)

if __name__ == '__main__':
    util.runServer(DictProxyServer())
