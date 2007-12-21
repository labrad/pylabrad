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

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from twisted.web import resource, server as webserver
from twisted.cred import portal, checkers, credentials
from nevow import loaders, rend, tags as T, entities as E, \
                  url, inevow, guard, athena, static
from nevow.taglibrary import tabbedPane
from nevow.inevow import ISession
from zope.interface import implements

from labrad.config import ConfigFile, configPath
from labrad.wrappers import AsyncClient

import os

REFRESH = '__refresh__'
IMAGES = '__images__'

RED = 'color:rgb(%d,%d,%d)' % (180,0,0)
GREEN = 'color:rgb(%d,%d,%d)' % (0,180,0)
GRAY = 'color:rgb(%d,%d,%d)' % (180,180,180)

HERE_DIR = os.path.split(os.path.abspath(__file__))[0]
IMAGE_DIR = os.path.join(HERE_DIR, 'images')
IMG = lambda name, **kw: T.img(src=url.root.child(IMAGES).child(name + '.png'),
                               style='border:0px;', **kw)

class ImageResource(rend.Page):
    def childFactory(self, ctx, name):
        return static.File(os.path.join(IMAGE_DIR, name),
                           defaultType='image/png')

# redirect to root page and clear query parameters
goHome = lambda _: (url.root.clear(), ())

def _nodes(cxn):
    servers = sorted(cxn.servers.keys())
    return [s for s in servers if s.startswith('node')]

class ServerResource(rend.Page):
    addSlash = True

    def locateChild(self, ctx, segments):
        srv = self.original
        setting = segments[0]
        if setting not in srv.settings:
            return self, ()
        data = ctx.arg('data')
        d = srv.settings[setting](data)
        def saveException(failure):
            failure.trap(Exception)
            ISession(ctx).fields['flash'] = (data, srv.name, setting, failure)
        return d.addErrback(saveException).addCallback(goHome)

    def data_settings(self, ctx, srv):
        settings = self.original.settings.values()
        return sorted(settings, key=lambda s: s.ID)

    def render_server(self, ctx, data):
        ctx.tag.fillSlots('name', self.original._labrad_name)
        ctx.tag.fillSlots('descr', self.original.__doc__)
        ctx.tag.fillSlots('notes', self.original.notes)
        return ctx.tag

    def render_setting(self, ctx, setting):
        return ctx.tag[
            T.h3["(%d) '%s'" % (setting.ID, setting._labrad_name)],
            T.p[setting.__doc__],
            T.h4['Accepted types:'],
            T.ul[(T.li[s] for s in setting.accepts)],
            T.h4['Returned types:'],
            T.ul[(T.li[s] for s in setting.returns)],
            T.p[setting.notes],
        ]
    
    docFactory = loaders.stan(
        T.html[
            T.head[
                T.title['LabRAD Server'],
            ],
            T.body[
                T.p[T.a(href=url.root.clear())['<< back']],
                T.div(render=T.directive('server'))[
                    T.h1[T.slot('name')],
                    T.p[T.slot('descr')],
                    T.p[T.slot('notes')],
                    T.h4['Settings'],
                    T.ul(data=T.directive('settings'), render=rend.sequence)[
                        T.li(pattern='item', render=T.directive('setting')),
                        T.li(pattern='empty')[T.td['No registered settings.']]
                    ]
                ]
            ]
        ])

class ControllerPage(rend.Page):
    addSlash = True

    @inlineCallbacks
    def childFactory(self, ctx, name):
        cxn = self.realm.cxn
        yield cxn.refresh()
        if not cxn:
            returnValue(self)
        elif name in cxn.servers:
            srv = ServerResource(cxn.servers[name])
            srv.realm = self.realm
            returnValue(srv)
        elif name == IMAGES:
            returnValue(ImageResource(name))
        elif name == REFRESH:
            returnValue(cxn.refresh().addCallback(lambda r: self))
        returnValue(rend.NotFound)

    def data_pages(self, ctx, data):
        cxn = self.realm.cxn
        if cxn:
            mgr = cxn.manager
            return {'pages': (('Servers', ServerList(cxn)),
                              ('Security', IPInfo(mgr)))}
        else:
            return {'pages': (('Servers', T.p['Not connected to LabRAD...']),
                              ('Security', T.p['Not connected to LabRAD...']))}

    docFactory = loaders.stan(
        T.html[
            T.head[
                T.title['LabRAD Controller'],
                tabbedPane.tabbedPaneGlue.inlineGlue
            ],
            T.body[
                T.p[ T.a(href=guard.LOGOUT_AVATAR)['Logout'], ' | ',
                     T.a(href=url.root.child(REFRESH))['Refresh'] ],
                T.invisible(data=T.directive('pages'),
                            render=tabbedPane.tabbedPane)
            ]
        ])

class ServerList(rend.Fragment):
    def render_header(self, ctx, data):
        cxn = self.original
        nodes = [n.split('_',1)[1] for n in _nodes(cxn)]
        im = IMG('arrow_refresh')
        return ctx.tag[
            T.td[T.b['server']],
            [T.td(colspan=3)[T.b[n], E.nbsp,
             T.a(href=url.root.child('node_'+n).child('refresh'))[im]]
             for n in nodes]
        ]

    @inlineCallbacks
    def getNodeInfo(self, node):
        p = node.packet()
        p.available_servers()
        p.running_servers()
        p.local_servers()
        resp = yield p.send()
        available = resp.available_servers
        running = resp.running_servers
        local = resp.local_servers

        ninfo = {}
        rundict = dict(running)
        for n in available:
            ninfo[n] = rundict.get(n, ''), n in rundict, n in local
        returnValue(ninfo)
    
    @inlineCallbacks
    def data_servers(self, ctx, data):
        cxn = self.original
        nodes = _nodes(cxn)
        serversInfo = {}

        ninfo = yield DeferredList([self.getNodeInfo(cxn[n]) for n in nodes])
        for node, (success, result) in zip(nodes, ninfo):
            if not success:
                continue
            for server, info in result.iteritems():
                if server not in serversInfo:
                    serversInfo[server] = [server, False, {}]
                s = serversInfo[server]
                s[1] |= info[1] # whether server is running anywhere
                s[2][node] = info
        sinfo = [serversInfo[n] for n in sorted(serversInfo.keys())]
        returnValue(sinfo)

    def render_server(self, ctx, data):
        cxn = self.original
        nodes = _nodes(cxn)
        exc = ISession(ctx).fields.get('flash', None)
        excHere = False

        baseName, running_anywhere, info = data
        instanceName = None
        node_actions = []
        for node in nodes:
            if node in info:
                name, running, local = info[node]
                # controls are start, stop, restart
                if running:
                    color, state, enabled = GREEN, 'running', [0, 1, 1]
                    instanceName = name
                elif not local and running_anywhere:
                    color, state, enabled = GRAY, 'running', [0, 0, 0]
                else:
                    color, state, enabled = RED, 'stopped', [1, 0, 0]
            else:
                color, state, enabled = GRAY, 'unavailable', [0, 0, 0]
            if exc is not None and \
               (exc[0] == name or exc[0] == baseName) and exc[1] == node:
                color = RED
                state = 'error!'
                del ISession(ctx).fields['flash']
                excHere = True
            controls = []
            for act, enabled, img in zip(['start', 'stop', 'restart'], enabled,
                                         ['add', 'delete', 'arrow_refresh']):
                if enabled:
                    ln = url.here.child(node).child(act)
                    if act == 'start':
                        ln = ln.add('data', baseName)
                    else:
                        ln = ln.add('data', name)
                    img = IMG(img, alt=act)
                    item = T.a(href=ln)[img]
                else:
                    item = IMG(img + '_gray')
                controls.append(item)
            if excHere:
                node_actions.append((
                    T.td[T.b(title=str(exc[3]), style=color)[state]],
                    T.td[controls]
                ))
                excHere = False
            else:
                node_actions.append((
                    T.td[T.span(style=color)[state]],
                    T.td[controls]
                ))
        if running_anywhere:
            name = T.a(href=instanceName)[baseName]
        else:
            name = baseName
        return ctx.tag[T.td[name], node_actions]

    docFactory = loaders.stan(
        T.table(data=T.directive('servers'), render=rend.sequence)[
            T.tr(pattern='header', render=T.directive('header')),
            T.tr(pattern='item', render=T.directive('server')),
            T.tr(pattern='empty')[T.td['No servers available.']]
        ])

class IPInfo(rend.Fragment):
    @inlineCallbacks
    def data_iplist(self, ctx, data):
        p = self.original.packet()
        p.whitelist()
        p.blacklist()
        ans = yield p.send()
        wl, bl = ans.whitelist, ans.blacklist
        returnValue([(True, ip) for ip in wl] + [(False, ip) for ip in bl])

    def render_iplist(self, ctx, info):
        allowed, addr = info
        if allowed:
            action, descr, img = 'blacklist', 'remove', 'tick'
        else:
            action, descr, img = 'whitelist', 'allow', 'cross'
        link = url.here.child('manager').child(action).add('data', addr)
        return ctx.tag[
            T.td[T.a(href=link)[IMG(img, alt=descr)]], T.td[addr]
        ]

    docFactory = loaders.stan(
        T.div[
            T.h2['IP List'],
            T.table(data=T.directive('iplist'), render=rend.sequence)[
                T.tr(pattern='item', render=T.directive('iplist')),
                T.tr(pattern='empty')[ 'none.' ]
            ],
            T.form(action=url.here.child('manager').child('whitelist'),
                   method='post')[
                T.input(type='text', name='data'),
                T.input(type='submit', value='Add')
            ]
        ])

class LoginPage(rend.Page):
    addSlash = True

    def locateChild(self, ctx, segments):
        """Redirect from anywhere to the login page root."""
        if len(segments) > 1:
            return url.root, ()
        else:
            return self, ()
    
    docFactory = loaders.stan(
        T.html[
            T.head[ T.title['labrad Controller - Login'] ],
            T.body[
                T.form(action=guard.LOGIN_AVATAR, method='post')[
                    T.table[
                        T.tr[
                            T.td[ 'Username:' ],
                            T.td[ T.input(type='text', name='username') ],
                        ],
                        T.tr[
                            T.td[ 'Password:' ],
                            T.td[ T.input(type='password', name='password') ],
                        ]
                    ],
                    T.input(type='submit', value='Log in'),
                ]
            ]
        ])

class labradRealm:
    """A simple implementor of cred's IRealm.

    For web, this checks the login and gives a login page or the
    actual page, as appropriate.
    """
    implements(portal.IRealm)

    reconnectDelay = 10

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.connected = False
        self.cxn = None
        self._connect()

    def _connect(self):
        cxn = AsyncClient(name='Web Interface Client')
        d = cxn.connect(self.host, self.port)
        d.addCallbacks(self._connectionSucceeded, self._connectionFailed)
        d = cxn.notifyOnDisconnect()
        d.addBoth(self._connectionFailed)

    def _connectionSucceeded(self, c):
        try:
            if c.connected:
                self.cxn = c
                self.connected = True
                print 'Connected to manager %s:%d.' % (self.host, self.port)
            else:
                self._reconnect()
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

    def requestAvatar(self, avatarId, mind, *interfaces):
        for iface in interfaces:
            if iface is inevow.IResource:
                if avatarId is checkers.ANONYMOUS:
                    resc = LoginPage()
                else:
                    resc = ControllerPage(avatarId)
                resc.realm = self
                return (inevow.IResource, resc, lambda: None)

        raise NotImplementedError("Can't support that interface.")


### Application setup

def labradNevowPage(host, port):
    realm = labradRealm(host, port)
    porta = portal.Portal(realm)

    try:
        passFile = ConfigFile('controller.ini')
    except:
        passFile = ConfigFile('controller-template.ini')
        
    myChecker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
    for section in passFile.sections():
        try:
            myChecker.addUser(passFile.get(section, 'username'),
                              passFile.get(section, 'password'))
        except Exception, e:
            print e
    
    porta.registerChecker(myChecker)
    porta.registerChecker(checkers.AllowAnonymousAccess(), credentials.IAnonymous)
    res = guard.SessionWrapper(porta)
    res.sessionLifetime = 86400 # one day
    
    return res

