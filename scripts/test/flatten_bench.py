import time

from labrad import types as T

data = [('0'*16, '0'*128, '0'*512)] * 20

def run():
    for _ in xrange(10000):
        T.flatten(data)

if __name__ == '__main__':
    start = time.time()
    run()
    end = time.time()
    elapsed = end - start
    print "elapsed:", elapsed
