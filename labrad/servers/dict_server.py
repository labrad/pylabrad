from labrad import util
from labrad.server import LabradServer, setting

class DictServer(LabradServer):
    name = "dict_server"

    @setting(10, key='s', value='?')
    def set(self, c, key, value=None):
        c[key] = value

    @setting(11, key='s')
    def get(self, c, key):
        return c[key]

if __name__ == '__main__':
    util.runServer(DictServer())
