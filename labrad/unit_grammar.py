#!/usr/bin/env python

from pyparsing import (Word, Literal, Group,
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
