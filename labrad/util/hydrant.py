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
labrad.util.hydrant

Generate random LabRAD data for use in testing.
"""

from __future__ import print_function

from builtins import input, range

from datetime import datetime, timedelta
from random import choice, randint, gauss

from labrad import types as T

def randType(noneOkay=True, listOkay=True, nStructs=0):
    choices = [
        T.TNone,
        T.TBool,
        T.TInt,
        T.TUInt,
        T.TStr,
        T.TBytes,
        T.TTime,
        lambda: T.TValue(randUnits()),
        lambda: T.TComplex(randUnits()),
        lambda: T.TCluster(*[randType(noneOkay=False, nStructs=nStructs+1)
                              for _ in range(randint(1, 5))]),
        lambda: T.TList(randType(noneOkay=False, listOkay=False,
                                  nStructs=nStructs+1),
                         depth=randint(1, 3)),
    ]
    if not noneOkay:
        choices = choices[1:]
    if nStructs >= 3:
        choices = choices[:-2]
    elif not listOkay:
        choices = choices[:-1]
    return choice(choices)()

def randUnits():
    return choice(('', 's', 'ms', 'us', 'm', 'm/s', 'V^2/Hz', 'V/Hz^1/2'))

def randValue(t):
    if isinstance(t, T.TNone): return genNone()
    if isinstance(t, T.TBool): return genBool()
    if isinstance(t, T.TInt): return genInt()
    if isinstance(t, T.TUInt): return genWord()
    if isinstance(t, T.TStr): return genStr()
    if isinstance(t, T.TBytes): return genStr()
    if isinstance(t, T.TTime): return genTime()
    if isinstance(t, T.TComplex): return genComplex(t.unit) # check complex before value
    if isinstance(t, T.TValue): return genValue(t.unit)
    if isinstance(t, T.TCluster): return genCluster(*t.items)
    if isinstance(t, T.TList): return genList(t.elem, t.depth)


def genNone(): return None
def genBool(): return choice((True, False))
def genInt(): return int(randint(-2**31, 2**31-1))
def genWord():
    value = randint(0, 2**32-1)
    try:
        return long(value)
    except NameError:
        return value  # python 3 has no long type

def genStr():
    return ''.join(chr(randint(0, 255)) for _ in range(randint(0, 100)))

def genTime():
    diff = timedelta(seconds=randint(-2**20, 2**20),
                     microseconds=randint(-2**20, 2**20))
    return datetime.now() + diff

def genValue(unit=None):
    return T.Value(gauss(0, 1), unit)

def genComplex(unit=None):
    return T.Complex(complex(gauss(0, 1), gauss(0, 1)), unit)

def genList(elem, depth=1):
    lengths = [randint(1, 2**(5-depth)) for _ in range(depth)]
    def genNDList(ls):
        if len(ls) == 1:
            return [randValue(elem) for _ in range(ls[0])]
        else:
            return [genNDList(ls[1:]) for _ in range(ls[0])]
    return genNDList(lengths)

def genCluster(*items):
    return tuple(randValue(t) for t in items)


def hoseDown(setting, n=1000, silent=True):
    for _ in range(n):
        t = randType()
        v = randValue(t)
        if not silent:
            print(t)
        try:
            resp = setting(v)
            assert v == resp
        except:
            print('problem:', str(t), repr(t))
            print(str(T.flatten(v)[1]), str(T.flatten(resp)[1]))
            raise

def hoseDataVault(dv, n=1000, silent=True):
    for i in range(n):
        t = randType(noneOkay=False)
        v = randValue(t)
        if not silent:
            print(t)
        try:
            pname = 'p%03s' % i
            dv.add_parameter(pname, v)
            resp = dv.get_parameter(pname)
            assert v == resp
        except:
            print('problem:', str(t), repr(t))
            print(str(T.flatten(v)[1]), str(T.flatten(resp)[1]))
            raise


if __name__ == '__main__':
    import labrad
    cxn = labrad.connect()
    try:
        hoseDown(cxn.python_test_server.echo, n=10000, silent=False)
    except Exception as e:
        print(e)
    else:
        print('Success!')
    finally:
        print('press <enter> to finish...')
        input()
