#!/usr/bin/python
"""Measure some performance figures on the unit library

run_tests will run every function named perf_X, and create
a dictionary of the timing results.  perf_ tests can have
an optional argument 'N' which is a number of iterations
to run.
"""
import argparse
import json
import random
import timeit
import xml.etree.ElementTree as ET

import numpy as np

import labrad.units as U


unit_list = [x for x in U._unit_table.values() if x.offset == 0]


def random_unit():
    return random.choice(unit_list)


def perf_mul_float(N=1000):
    a = 1.0
    b = 230.0
    for j in range(N):
        c = a * b


def perf_mul_value_random(N=1000):
    for j in range(N):
        u1 = random_unit()
        u2 = random_unit()
        c = (1.0*u1) * (1.0*u2)


def perf_mul_unit_random(N=1000):
    for j in range(N):
        u1 = random_unit()
        u2 = random_unit()
        up = u1 * u2


def perf_mul_unit_cached(N=1000):
    u1 = random_unit()
    u2 = random_unit()
    for j in range(N):
        up = u1 * u2


def perf_mul_value_cached(N=1000):
    u1 = random_unit()
    u2 = random_unit()
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
        w = random.random() * .1 * U.GHz
        phi = random.random()*np.pi
        z[j*20:(j+1)*20] = (1-np.cos(t_cos*w_cos))*np.exp(1j*w*t[j*20:(j+1)*20]+phi)
    return z


def perf_envelope_no_unit(N=1000):
    t = np.arange(20*N)
    t_cos = np.arange(20)
    w_cos = np.pi * 2 / 20
    z = np.zeros(20*N, dtype=np.complex128)
    for j in range(N):
        w = random.random() * .1
        phi = random.random() * np.pi
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


def run_tests(func_prefix='perf_', key_prefix='labrad.units.'):
    stats = {}
    g = globals()
    for name in g.keys():
        if name.startswith(func_prefix):
            key = key_prefix + name[len(func_prefix):]
            result = timeit.repeat(g[name], number=10, repeat=3)
            stats[key] = min(result)/10000 * U.s
    return stats


def main():
    parser = argparse.ArgumentParser(description='Run unit tests')
    parser.add_argument('--format', nargs='?',
                        choices=['xml', 'json'], default='json',
                        help='ouptut format in which to report results')

    args = parser.parse_args()

    result = run_tests()

    if args.format == 'json':
        print json.dumps({k: v['ms'] for k, v in result.items()}, indent=2)
    else:
        root = ET.Element('build')
        for k, v in sorted(result.items()):
            child = ET.SubElement(root, 'statisticValue',
                                  key=k, value='{:f}'.format(v['ms']))
        print ET.tostring(root)


if __name__ == "__main__":
    main()
