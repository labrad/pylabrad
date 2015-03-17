# This module implements a LRU cache.  There are many modules like it,
# but this one is mine.
#
# The basic idea of a cache is that you have some function f(x) that is
# expensive (in CPU or IO) to compute, and for which we often evaluate for
# the same x many times.  If f(x) depends only on x and has no side effects,
# you can just remember (memoize) the result after the first call, and subsequent
# calls just return the cached result.
#
# There are a couple of problems with that.  First, a generic problem: caches
# need a mechanism to discard entries or they grow without bound.  In our
# case, the cache values may be relatively large arrays: 100 KB - 1 MB.  If
# we store 1000 entries, that can take up to 1 GB of memory.  So real caches
# eventually need a mechanism to discard entries.  The most common algorithms
# are least-frequently-used and least-recently-used.  When the cache reaches
# a fixed size, the indicated elements are discarded.  Often it is computationally
# easier to find some approximation of the least-recently-used element.
#
# The second problem is that in our case 'x' itself may be quite large (a numpy
# array of similar size to f(x).  Locating an item x by value may be excessively
# expensive.  numpy arrays are not hashable, and not immutable, complicating
# matters further.  Therefore, it is the client's responsibility to calculate a
# unique key that represents the data.  A common pattern will be to require that
# x be an array of equally spaced elements, which can be uniquely described by the
# the first and last elements, and the length.

from collections import namedtuple
from functools import update_wrapper
from threading import RLock

import numpy as np

_CacheInfo = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])

class _HashedSeq(list):
    __slots__ = 'hashvalue'

    def __init__(self, tup, hash=hash):
        self[:] = tup
        self.hashvalue = hash(tup)

    def __hash__(self):
        return self.hashvalue

def make_key(args, kwds, typed=False,
             kwd_mark=(object(),),
             fasttypes=[int, str, frozenset, type(None)]):
    """Make a cache key from optionally typed positional and keyword arguments.

    Raises TypeError if any items in args or values in kwds are not hashable.
    """
    key = tuple(args)
    if kwds:
        sorted_items = sorted(kwds.items())
        key += kwd_mark
        for item in sorted_items:
            key += item
    if typed:
        key += tuple(type(v) for v in args)
        if kwds:
            key += tuple(type(v) for k, v in sorted_items)
    elif len(key) == 1 and type(key[0]) in fasttypes:
        return key[0]
    return _HashedSeq(key)

class fast_str(str):
    """String class with a hash function that is fast for very long strings.

    Note that str(a) and fast_str(a) will compare equal but
    have different hash values.  Do not use unless you understand the
    ramifications of that.
    """
    def __hash__(self):
        if len(self) > 64:
            return str.__hash__(self[0:32:2] + self[-32::2])
        else:
            return str.__hash__(self)

def keyfunc_ndarray(a):
    """Key function for a numpy array.

    Uses the string representation of the raw data,
    and uses the fast_str hash function for maximum performance.
    """
    a = np.asarray(a)
    return (a.shape, a.dtype, fast_str(a.tostring()))


class LRUCache(object):
    """Least-recently-used cache dictionary.

    Get cached results by calling the 'get' method, passing a key to lookup
    and a function to be called with specified positional and keyword args
    to compute the result if the key is not found. The cache will store up
    to *maxsize* elements, tossing out the least-recently used element
    when the maximum size is reached.

    If *maxsize* is set to None, the LRU features are disabled and the cache
    can grow without bound.

    See:  http://en.wikipedia.org/wiki/Cache_algorithms#Least_Recently_Used

    Based on a backport of functools.lru_cache from python 3.3+:
    http://code.activestate.com/recipes/578078-py26-and-py30-backport-of-python-33s-lru-cache/

    Implementation details:
    The LRU cache consists of a dictionary (self.cache) and a circular
    doubly-linked list. The dictionary contains a mapping from keys to
    linked-list elements, and each linked list element contains 4 entries:
    the list prev- and next-pointers, the key, and the cached result value.
    """

    PREV, NEXT, KEY, RESULT = 0, 1, 2, 3 # names for the link fields

    def __init__(self, maxsize=128):
        self.maxsize = maxsize

        # depending on maxsize, choose the implementation of 'get'
        # based on whether or not we need caching and size limitation
        if maxsize == 0:
            self.get = self._get_nocache
        elif maxsize is None:
            self.get = self._get_nomax
        else:
            self.get = self._get

        self.hits = self.misses = 0
        self.cache = {}
        self.lock = RLock() # because linkedlist updates aren't threadsafe
        root = self.root = [] # root of the circular doubly-linked list
        root[:] = [root, root, None, None] # link the list to itself

    def _get_nocache(self, key, fn, *args, **kwds):
        """no caching, just do a statistics update after a successful call"""
        result = fn(*args, **kwds)
        self.misses += 1
        return result

    def _get_nomax(self, key, fn, *args, **kwds):
        """simple caching without ordering or size limit"""
        result = self.cache.get(key, self.root) # root used here as a unique not-found sentinel
        if result is not self.root:
            self.hits += 1
            return result
        result = fn(*args, **kwds)
        self.cache[key] = result
        self.misses += 1
        return result

    def _get(self, key, fn, *args, **kwds):
        """size-limited caching that tracks accesses by recency"""
        with self.lock:
            link = self.cache.get(key)
            if link is not None:
                # record recent use of the key by moving it to the front of the list
                root = self.root
                link_prev, link_next, key, result = link
                link_prev[self.NEXT] = link_next
                link_next[self.PREV] = link_prev
                last = root[self.PREV]
                last[self.NEXT] = root[self.PREV] = link
                link[self.PREV] = last
                link[self.NEXT] = root
                self.hits += 1
                return result
        result = fn(*args, **kwds)
        with self.lock:
            root = self.root
            if key in self.cache:
                # getting here means that this same key was added to the
                # cache while the lock was released.  since the link
                # update is already done, we need only return the
                # computed result and update the count of misses.
                pass
            elif len(self.cache) >= self.maxsize:
                # use the old root to store the new key and result
                oldroot = root
                oldroot[self.KEY] = key
                oldroot[self.RESULT] = result
                # empty the oldest link and make it the new root
                root = self.root = oldroot[self.NEXT]
                oldkey = root[self.KEY]
                oldvalue = root[self.RESULT]
                root[self.KEY] = root[self.RESULT] = None
                # now update the cache dictionary for the new links
                del self.cache[oldkey]
                self.cache[key] = oldroot
            else:
                # put result in a new link at the front of the list
                last = root[self.PREV]
                link = [last, root, key, result]
                last[self.NEXT] = root[self.PREV] = self.cache[key] = link
            self.misses += 1
        return result

    def info(self):
        """Report cache statistics"""
        with self.lock:
            return _CacheInfo(self.hits, self.misses, self.maxsize, len(self.cache))

    def clear(self):
        """Clear the cache and cache statistics"""
        with self.lock:
            self.cache.clear()
            root = self.root
            root[:] = [root, root, None, None]
            self.hits = self.misses = 0

    def evict(self, key):
        """Remove the given key from the cache."""
        with self.lock:
            if key in self.cache:
                link = self.cache[key]
                # remove item from the lru linked list
                link[self.PREV][self.NEXT] = link[self.NEXT]
                link[self.NEXT][self.PREV] = link[self.PREV]
                # remove item from the cache
                del self.cache[key]

def lru_cache(maxsize=128, typed=False):
    """Least-recently-used cache decorator.

    If *maxsize* is set to None, the LRU features are disabled and the cache
    can grow without bound.

    If *typed* is True, arguments of different types will be cached separately.
    For example, f(3.0) and f(3) will be treated as distinct calls with
    distinct results.

    Uses the make_key function to create a hash key for arguments passed
    to the decorated function. Hence, arguments to the cached function
    must be hashable, or the call will fail with a TypeError.

    View the cache statistics named tuple (hits, misses, maxsize, currsize) with
    f.cache_info().  Clear the cache and statistics with f.cache_clear().
    Access the underlying function with f.__wrapped__.

    Based on a backport of functools.lru_cache from python 3.3+:
    http://code.activestate.com/recipes/578078-py26-and-py30-backport-of-python-33s-lru-cache/
    """

    def decorating_function(user_function):

        cache = LRUCache(maxsize)

        def wrapper(*args, **kwds):
            key = make_key(args, kwds)
            return cache.get(key, user_function, *args, **kwds)

        def cache_info():
            """Report cache statistics"""
            return cache.info()

        def cache_clear():
            """Clear the cache and cache statistics"""
            cache.clear()

        def cache_evict(key):
            """Remove the given key from the cache."""
            cache.evict(key)

        wrapper.__wrapped__ = user_function
        wrapper.cache_info = cache_info
        wrapper.cache_clear = cache_clear
        wrapper.cache_evict = cache_evict
        return update_wrapper(wrapper, user_function)

    return decorating_function
