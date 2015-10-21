#!/usr/bin/python
"""Measure some performance figures on the unit library

run_tests will run every function named perf_X, and create
a dictionary of the timing results.  perf_ tests can have
an optional argument 'N' which is a number of iterations
to run.
"""
import labrad.units as U
import numpy as np
import timeit

unit_list = [ x for x in U._unit_table.values() if x.offset==0]

def perf_mul_float(N=1000):
    a = 1.0
    b = 230.0
    for j in range(N):
        c = a * b

def perf_mul_value_random(N=1000):
    for j in range(N):
        u1 = unit_list[np.random.randint(len(unit_list))]
        u2 = unit_list[np.random.randint(len(unit_list))]
        c = (1.0*u1) * (1.0*u2)

def perf_mul_unit_random(N=1000):
    for j in range(N):
        u1 = unit_list[np.random.randint(len(unit_list))]
        u2 = unit_list[np.random.randint(len(unit_list))]
        up = u1 * u2

def perf_mul_unit_cached(N=1000):
    u1 = unit_list[np.random.randint(len(unit_list))]
    u2 = unit_list[np.random.randint(len(unit_list))]
    for j in range(N):
        up = u1 * u2
    
def perf_mul_value_cached(N=1000):
    u1 = unit_list[np.random.randint(len(unit_list))]
    u2 = unit_list[np.random.randint(len(unit_list))]
    for j in range(N):
        c = (1.0*u1) * (1.0*u2)

def perf_add_value_equal(N=1000):
    u1 = U.m
    for j in range(N):
        c = (1*u1) + (1*u1)

def perf_add_value_unequal(N=1000):
    u1 = U.m
    u2 = U.nm
    for j in range(N):
        c = (1*u1) + (1*u2)

def perf_envelope_unit(N=1000):
    t = np.arange(20*N)*U.ns
    t_cos = np.arange(20)*U.ns
    w_cos = np.pi * 2 * U.GHz / 20
    z = np.zeros(20*N, dtype=np.complex128)
    for j in range(N):
        w = np.random.rand() * .1 * U.GHz
        phi = np.random.rand()*np.pi
        z[j*20:(j+1)*20] = (1-np.cos(t_cos*w_cos))*np.exp(1j*w*t[j*20:(j+1)*20]+phi)
    return z
                              

def perf_envelope_no_unit(N=1000):
    t = np.arange(20*N)
    t_cos = np.arange(20)
    w_cos = np.pi * 2 / 20
    z = np.zeros(20*N, dtype=np.complex128)
    for j in range(N):
        w = np.random.rand() * .1
        phi = np.random.rand()*np.pi
        z[j*20:(j+1)*20] = (1-np.cos(t_cos*w_cos))*np.exp(1j*w*t[j*20:(j+1)*20]+phi)
    return z

def perf_mul_array_unit(N=1000):
    a1 = np.arange(1000)*U.ns
    a2 = np.arange(1000)*U.GHz
    for j in range(N):
        a3 = a1 * a2
    
def perf_mul_array(N=1000):
    a1 = np.arange(1000)
    a2 = np.arange(1000)
    for j in range(N):
        a3 = a1 * a2

def run_tests():
    stats = {}
    g = globals()
    for k in g.keys():
        if k.startswith('perf_'):
            result = timeit.repeat(g[k], number=10, repeat=3)
            stats[k[5:]] = min(result)/(10000) * U.s
    return stats

def main():
    result = run_tests()
    for k in sorted(result.keys()):
        print '%s: %6g us' % (k, result[k]['us'])

if __name__ == "__main__":
    main()
