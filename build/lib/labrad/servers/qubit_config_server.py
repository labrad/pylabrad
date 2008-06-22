#!c:\python25\python.exe

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

from labrad import types as T, util
from labrad.server import LabradServer, setting
from labrad.errors import Error
from twisted.internet import defer, reactor
from twisted.internet.defer import inlineCallbacks

import os
import shelve
import time

DATADIR = os.path.split(os.path.abspath(__file__))[0]
SHELF_PREFIX = 'qubit_config_server.'
SHELF_NAME = lambda n: os.path.join(DATADIR, SHELF_PREFIX + n)

class WiringError(Error):
    """A problem was found in the wiring configuration."""
    code = 17

class Shelvable(object):
    def __init__(self, parent, name, state=None):
        self.parent = parent
        self.name = name
        if state:
            self.load(state)

    def load(self, state):
        """Initialize from a previously saved state."""

    def save(self):
        """Save the state of this object."""

    def __repr__(self):
        return '<%s: "%s">' % (self.__class__.__name__, self.name)

class Qubit(Shelvable):
    memory = []
    uwave = []
    meas = []
    wiring = []
    delays = [T.Value(0, 'ns'), T.Value(0, 'ns')]

    def load(self, state):
        self.memory = state['memory']
        self.uwave = state['uwave']
        self.meas = state['meas']
        self.wiring = state['wiring']

    def save(self):
        return {'memory': self.memory,
                'uwave': self.uwave,
                'meas': self.meas,
                'wiring': self.wiring}

def addTrigger(sram, start=4, duration=12, ID=15):
    """Add a trigger pulse to an array of SRAM content."""
    for i in range(start, start+duration):
        sram[i] |= ID << 28
    return sram

class Board(Shelvable):
    role = 'none'

    @inlineCallbacks
    def update_fpga(self):
        if not hasattr(self, 'ctx'):
            cxn = self.parent.client
            self.fpga = cxn.ghz_dacs
            self.ctx = self.fpga.context()
            yield self.fpga.select_device(self.name, context=self.ctx)
        p = self.fpga.packet()
        p.sram_address(0)
        p.sram(self.sram)
        p.memory(self.memory)
        resp = yield p.send(context=self.ctx)
        returnValue(resp)

    def run_sequence(self, reps):
        return self.fpga.run_sequence(reps, context=self.ctx)

    def load(self, state):
        self.role = state['role']

    def save(self):
        return {'role': self.role}

class Config(Shelvable):
    qubit_order = []
    daisy_chain = []
    daisy_delays = []
    
    qubits = {}
    boards = {}
    
    def load(self, state):
        def loadDict(dict_, cls):
            d = {}
            for n, data in dict_.items():
                d[n] = cls(self.parent, n, data)
            return d
        self.qubits = loadDict(state['qubits'], Qubit)
        self.boards = loadDict(state['boards'], Board)
        self.qubit_order = state['qubit_order']
        self.daisy_chain = state['daisy_chain']
        self.daisy_delays = state['daisy_delays']

    def save(self):
        def saveDict(dict_):
            d = {}
            for n, obj in dict_.items():
                d[n] = obj.save()
            return d
        return {'qubits': saveDict(self.qubits),
                'boards': saveDict(self.boards),
                'qubit_order': self.qubit_order,
                'daisy_chain': self.daisy_chain,
                'daisy_delays': self.daisy_delays}

    def sanityCheck(self):
        boards = self.boards
        qubits = self.qubits
        qubit_order = self.qubit_order
        daisy_chain = self.daisy_chain

        # lookup the boards in daisy_chain
        for n in daisy_chain:
            if n not in boards:
                raise WiringError('Unknown board "%s".' % n)
            b = boards[n]
            if b.role not in ['meas', 'uwave']:
                raise WiringError('Unknown role "%s" for board "%s".' % (b.role, n))
            if b.role == 'uwave':
                b.uwave = None
            else:
                b.meas = {'A': None, 'B': None}
            b.memory = None

        qubit_reorder_list = [None] * len(qubit_order)
        sram_len = None
        default_mem = None
        padding = [0, 0]

        # check the wiring configuration
        for q_index, qubit in enumerate(qubit_order):
            if qubit not in qubits:
                raise WiringError('Unknown qubit "%s".' % qubit)
            q = qubits[qubit]

            if len(q.wiring) != 4:
                raise WiringError('Qubit "%s" is improperly wired.' % qubit)
            timing, uwave, meas, measChan = q.wiring
            for b in (timing, uwave, meas):
                if b not in boards:
                    raise WiringError('Qubit "%s": unknown board "%s".' % (qubit, b)) 
                if b not in daisy_chain:
                    raise WiringError('Qubit "%s": board "%s" not in daisy_chain.' % (qubit, b))
            if measChan not in ['A', 'B']:
                raise WiringError('Unknown measurement: qubit "%s", board "%s", channel "%s".' % (qubit, meas, measChan))
            
            b = boards[timing]
            if b.memory is not None:
                raise WiringError('Multiple memories, board "%s".' % timing)
            b.memory = q.memory

            b = boards[uwave]
            if b.role != 'uwave':
                raise WiringError('Qubit "%s": board "%s" is not a uwave board.' % (qubit, uwave))
            if b.uwave is not None:
                raise WiringError('Multiple uwaves, board "%s".' % uwave)
            b.uwave = q.uwave
            b.dt = int(q.delays[0])

            b = boards[meas]
            if b.role != 'meas':
                raise WiringError('Qubit "%s": board "%s" is not a meas board.' % (qubit, meas)) 
            if b.meas[measChan] is not None:
                raise WiringError('Multiple measurements, board "%s", channel "%s".' % (meas, measChan))
            b.meas[measChan] = q.meas
            idx = {'A':0, 'B':1}[measChan]
            b.dt[measChan] = int(q.delays[idx])

            b_index = daisy_chain.index(timing)
            qubit_reorder_list[q_index] = b_index
            default_mem = default_mem or q.memory
            sram_len = max((sram_len, len(q.uwave), len(q.meas)))
            delays = [d.value for d in q.delays]
            padding = [min([padding[0]] + delays),
                       max([padding[1]] + delays)]
        padding = [abs(int(d)) for d in delay_sizes]
        return qubit_reorder_list, default_mem, sram_len, padding 

class QubitServer(LabradServer):
    name = 'Qubit Server'

    def initServer(self):
        self.configs = shelve.open(SHELF_NAME('configs'))

    def stopServer(self):
        self.configs.close()

    def saveConfig(self, c):
        if 'config' in c:
            name = c['config'].name
            if name in self.configs:
                self.configs[name] = c['config'].save()

    def getConfig(self, c):
        if 'config' not in c:
            raise Exception('No open configuration.')
        return c['config']

    # general settings
    @setting(51, returns=['*s'])
    def list_configs(self, c):
        return sorted(self.configs.keys())

    @setting(52, name=['s'], returns=[''])
    def new_config(self, c, name):
        self.saveConfig(c)
        c['config'] = Config(self, name)

    @setting(53, name=['s'], returns=[''])
    def open_config(self, c, name):
        self.saveConfig(c)
        c['config'] = Config(self, name, self.configs[name])
        
    @setting(54, returns=[''])
    def save_config(self, c):
        conf = self.getConfig(c)
        self.configs[conf.name] = conf.save()

    @setting(55, returns=['s'])
    def inspect_config(self, c):
        return repr(self.getConf(c))

    @setting(56, returns=['s'])
    def check_config(self, c):
        conf = self.getConfig(c)
        conf.sanityCheck()
        return 'okay.'

    @setting(61, data=['*s'], returns=['', '*s'])
    def daisy_chain(self, c, data=None):
        conf = self.getConfig(c)
        if data is None:
            return conf.daisy_chain
        conf.daisy_chain = data

    @setting(62, data=['*w'], returns=['', '*w'])
    def daisy_delays(self, c, data=None):
        conf = self.getConfig(c)
        if data is None:
            return conf.daisy_delays
        conf.daisy_delays = data

    @setting(63, data=['*s'], returns=['', '*s'])
    def qubit_order(self, c, data=None):
        conf = self.getConfig(c)
        if data is None:
            return conf.qubit_order
        conf.qubit_order = data

    @setting(80, reps=['w'], returns=['*w'])
    def run_experiment(self, c, reps):
        """This is where all the magic happens."""
        conf = self.getConfig(c)
        f = conf.freq.value
        qubit_reorder_list, default_mem, sram_len, padding = conf.sanityCheck(conf)

        # make sure the extra padding keeps us at a multiple of 4
        padding[1] += 4 - sum(padding) % 4
        def addPadding(sram, dt, padding):
            return sram[:1] * (padding[0] + dt) + \
                   sram + \
                   sram[-1:] * (padding[1] - dt)

        # fix memory and SRAM for each board
        NOTHING = [0] * sram_len
        for n in conf.daisy_chain:
            # SRAM
            b = boards[n]
            if b.role == 'uwave':
                b.uwave = b.uwave or NOTHING
                b.uwave = addPadding(b.uwave, b.dt, padding)
                b.sram = b.DACify(f, uwave)
            elif b.role == 'meas':
                b.meas['A'] = b.meas['A'] or NOTHING
                b.meas['A'] = addPadding(b.meas['A'], b.dt['A'], padding)
                b.meas['B'] = b.meas['B'] or NOTHING
                b.meas['B'] = addPadding(b.meas['B'], b.dt['B'], padding)
                b.sram = b.DACify(f, b.meas['A'], b.meas['B'])
            addTrigger(b.sram) # for now, we'll just always trigger the scope

            # memory
            b.memory = b.memory or default_mem

        # update fpgas and run sequence in reverse order
        board_list = [boards[n] for n in conf.daisy_chain]
        
        updates = [b.update_fpga() for b in board_list[::-1]]
        yield defer.DeferredList(updates, fireOnOneErrback=True)
        
        #executions = [b.run_sequence(reps) for b in board_list[::-1]]
        #results = yield defer.DeferredList(executions, fireOnOneErrback=True)
        #results.reverse()

        p = self.client.fpga_device_server.packet()
        p.daisy_chain(conf.daisy_chain)
        p.start_delay(conf.daisy_delays)
        p.run_sequence(reps)
        results = p.send()

        # return results in qubit order, rather than board order
        for b_index in qubit_reorder_list:
            success, result = results[b_index]
            yield result[0]
            

    # qubit setup
    @setting(101, returns=['s'])
    def list_qubits(self, c):
        conf = self.getConfig(c)
        return sorted(conf.qubits.keys())

    @setting(102, name=['s'], returns=[''])
    def add_qubit(self, c, name):
        conf = self.getConfig(c)
        if name in conf.qubits:
            raise Exception('Qubit "%s" already exists.' % name)
        c['qubit'] = conf.qubits[name] = Qubit(self, name)

    @setting(103, name=['s'], returns=[''])
    def select_qubit(self, c, name):
        conf = self.getConfig(c)
        c['qubit'] = conf.qubits[name]

    @setting(104, returns=['s'])
    def inspect_qubit(self, c):
        return repr(c['qubit'])

    @setting(105, data=['*s'], returns=['*s', ''])
    def qubit_wiring(self, c, data=None):
        """timingBoard, uwaveBoard, measBoard, measChannel"""
        if data is None:
            return c['qubit'].wiring
        c['qubit'].wiring = data

    @setting(106, memory=['*w'], returns=['*w', ''])
    def qubit_memory(self, c, memory=None):
        if memory is None:
            return c['qubit'].memory
        c['qubit'].memory = memory

    @setting(107, uwave=['*w'], returns=['*w', ''])
    def qubit_uwave(self, c, uwave=None):
        if uwave is None:
            return c['qubit'].uwave
        c['qubit'].uwave = uwave

    @setting(108, meas=['*w'], returns=['*w', ''])
    def qubit_meas(self, c, meas=None):
        if meas is None:
            return c['qubit'].meas
        c['qubit'].meas = meas

    @setting(109, delays=['*v[ns]'], returns=['*v[ns]', ''])
    def qubit_delays(self, c, delays=None):
        if delays is None:
            return c['qubit'].delays
        c['qubit'].delays = delays


    # board setup
    @setting(201, returns=['*s'])
    def list_boards(self, c):
        conf = self.getConfig(c)
        return sorted(conf.boards.keys())

    @setting(202, name=['s'], returns=[''])
    def add_board(self, c, name):
        conf = self.getConfig(c)
        if name in conf.boards:
            raise Exception('Board "%s" already exists.' % name)
        c['board'] = conf.boards[name] = Board(self, name)

    @setting(203, name=['s'], returns=[''])
    def select_board(self, c, name):
        conf = self.getConfig(c)
        c['board'] = conf.boards[name]

    @setting(204, returns=['s'])
    def inspect_board(self, c):
        return repr(c['board'])

    @setting(205, role=['s'], returns=['s', ''])
    def board_role(self, c, role=None):
        if role is None:
            return c['board'].role
        c['board'].role = role


__server__ = QubitServer()

if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)
