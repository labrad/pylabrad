from labrad.pyparsing import (Word, Literal, Group, OneOrMore,
                              Forward, Optional, alphas, nums, stringEnd)

toInt = lambda s, l, t: [int(t[0])]

number = Word(nums).setParseAction(toInt)
name = Word(alphas)

power = Literal('^').suppress()
times = Literal('*').suppress()
divide = Literal('/').suppress()
one = Literal('1').suppress()
lparen = Literal('(').suppress()
rparen = Literal(')').suppress()
exponent = number.setResultsName('num') ^ \
           number.setResultsName('num') + divide + number.setResultsName('denom')
           #lparen + number.setResultsName('num') + rparen | \
           #lparen + number.setResultsName('num') + divide + number.setResultsName('denom') + rparen

single_unit = name.setResultsName('name') + Optional(power + exponent)
bare_unit = Group(single_unit).setResultsName('posexp', listAllMatches=True)
num_unit = Group(times + single_unit).setResultsName('posexp', listAllMatches=True)
denom_unit = Group(divide + single_unit).setResultsName('negexp', listAllMatches=True)

later_units = Forward()
later_units << (num_unit + Optional(later_units) |
                denom_unit + Optional(later_units))

unit = Forward()
unit << ((bare_unit | one + denom_unit) + Optional(later_units) + stringEnd)
