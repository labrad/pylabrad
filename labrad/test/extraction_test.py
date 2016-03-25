# test to benchmark the parsing of lists of string data
# this revealed a serious inefficiency in the implementation
# of labrad.types.Buffer, which is used in the parsing process.
# fixing the implementation resulted in a substantial performance gain.

import time

import numpy as np

from labrad import types

def timeIt(f, *a, **kw):
    start = time.time()
    result = f(*a, **kw)
    end = time.time()
    print f.__name__, '- elapsed:', end - start
    return result

def extractAverage(packets):
    data = ''.join(packets)
    Is, Qs = np.fromstring(data, dtype='<i2').reshape(-1, 2).astype(int).T
    return (Is, Qs)

def extract(packets):
    result = [data for src, dest, eth, data in packets]
    answer = extractAverage(result)
    return answer

mac = '01:23:45:67:89:ab'
eth = 1

packets = [(mac, mac, eth, '\x00'*44) for _ in range(9000)]
data, t, endianness = types.flatten(packets)

timeIt(extract, packets)
data, t, endianness = timeIt(types.flatten, packets)
timeIt(types.unflatten, data, t, endianness)
