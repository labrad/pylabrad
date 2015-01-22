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

import operator

def gcd(a, b):
    """Compute the greatest common divisor of two ints."""
    a, b = b, a % b
    if b == 0:
        return a
    else:
        return gcd(a, b)

class Ratio(object):
    """Object representing the ratio of two integers."""

    def __init__(self, num, denom=1):
        if isinstance(num, Ratio):
            self.num = num.num
            self.denom = num.denom
        else:
            self.num = num
            self.denom = denom
            self._reduce()

    def _reduce(self):
        d = gcd(self.num, self.denom)
        self.num /= d
        self.denom /= d
        # ensure denominator is positive
        if self.denom < 0:
            self.num *= -1
            self.denom *= -1

    def _cmp(self, other, op):
        if not isinstance(other, (int, long, float, Ratio)):
            return NotImplemented
        if not isinstance(other, Ratio):
            other = Ratio(other)
        return op(self.num * other.denom, other.num * self.denom)

    def __lt__(self, other): return self._cmp(other, operator.lt)
    def __le__(self, other): return self._cmp(other, operator.le)
    def __eq__(self, other): return self._cmp(other, operator.eq)
    def __ne__(self, other): return self._cmp(other, operator.ne)
    def __gt__(self, other): return self._cmp(other, operator.gt)
    def __ge__(self, other): return self._cmp(other, operator.ge)

    def isInteger(self):
        return abs(self.denom) == 1

    def __int__(self):
        if not self.isInteger():
            raise TypeError("Cannot convert %r to int." % self)
        return int(self.num)

    def __long__(self):
        if not self.isInteger():
            raise TypeError("Cannot convert %r to long." % self)
        return long(self.num)

    def __float__(self):
        return float(self.num) / float(self.denom)

    def __nonzero__(self):
        return self.num != 0

    def __repr__(self):
        return 'Ratio(%s,%s)' % (self.num, self.denom)

    def __str__(self):
        if self.denom == 1:
            return '%s' % self.num
        else:
            return '%s/%s' % (self.num, self.denom)

    def __neg__(self):
        return Ratio(-self.num, self.denom)

    def __pos__(self):
        return self

    def __abs__(self):
        return Ratio(abs(self.num), abs(self.denom))

    def __add__(self, other):
        if not isinstance(other, (int, long, Ratio)):
            return NotImplemented
        if not isinstance(other, Ratio):
            other = Ratio(other)
        num = self.num * other.denom + self.denom * other.num
        denom = self.denom * other.denom
        return Ratio(num, denom)

    __radd__ = __add__

    def __iadd__(self, other):
        sum = self + other
        self.num = sum.num
        self.denom = sum.denom

    def __sub__(self, other):
        return self + (-other)

    def __rsub__(self, other):
        return other + (-self)

    def __isub__(self, other):
        self.__iadd__(self, -other)

    def __mul__(self, other):
        if not isinstance(other, (int, long, Ratio)):
            return NotImplemented
        if not isinstance(other, Ratio):
            other = Ratio(other)
        num = self.num * other.num
        denom = self.denom * other.denom
        return Ratio(num, denom)

    __rmul__ = __mul__

    def __imul__(self, other):
        prod = self * other
        self.num = prod.num
        self.denom = prod.denom

    def __div__(self, other):
        if not isinstance(other, (int, long, Ratio)):
            return NotImplemented
        if not isinstance(other, Ratio):
            other = Ratio(other)
        num = self.num * other.denom
        denom = self.denom * other.num
        return Ratio(num, denom)

    __truediv__ = __div__

    def __rdiv__(self, other):
        if not isinstance(other, (int, long, Ratio)):
            return NotImplemented
        if not isinstance(other, Ratio):
            other = Ratio(other)
        num = other.num * self.denom
        denom = other.denom * self.num
        return Ratio(num, denom)

    def __idiv__(self, other):
        ratio = self / other
        self.num = ratio.num
        self.denom = ratio.denom
