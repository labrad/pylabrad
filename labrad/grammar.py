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
labrad.grammar

Grammars for parsing various LabRAD stuff with pyparsing.
"""

from labrad.pyparsing import (Word, Literal, Group,
                              Forward, Optional, alphas, nums, alphanums, stringEnd)

toInt = lambda s, l, t: [int(t[0])]

number = Word(nums).setParseAction(toInt)
name = Word(alphas + '%"\'\xE6\xF8', alphanums + '%"\'\xE6\xF8') # degree and mu

power = Literal('^').suppress()
times = Literal('*').suppress()
divide = Literal('/').suppress()
minus = Literal('-').setResultsName('neg')
one = Literal('1').suppress()
lparen = Literal('(').suppress()
rparen = Literal(')').suppress()
exponent = Optional(minus) + number.setResultsName('num') ^ \
           Optional(minus) + number.setResultsName('num') + divide \
                           + number.setResultsName('denom')

single_unit = name.setResultsName('name') + Optional(power + exponent)
bare_unit = Group(single_unit).setResultsName('posexp', listAllMatches=True)
num_unit = Group(times + single_unit).setResultsName('posexp', listAllMatches=True)
denom_unit = Group(divide + single_unit).setResultsName('negexp', listAllMatches=True)

later_units = Forward()
later_units << (num_unit + Optional(later_units) |
                denom_unit + Optional(later_units))

unit = Forward()
unit << ((bare_unit | one + denom_unit) + Optional(later_units) + stringEnd)
