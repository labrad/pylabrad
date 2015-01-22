''' unwrap.py -- a function that makes every paragraph in a text into a single long line
                  so that the text will look right in a "word wrapping" environment
                  (e.g. a word processor, HTML text box or a Palm Doc document).

    A paragraph is:
        1. an indented line followed by one or more unidented lines;
        2. two or more unidented lines with a blank line above.

    An indented line contains text and has leading spaces.
    An unindented line contains text but has no leading spaces.
    A blank line may contain spaces but not text; it may also be the start of the text.

    Anything other than those two types of paragraph (e.g. blocks of
    fully indented text, single lines) will be left alone.

        @    .  .
    glyn wave co nz
'''
#
# LICENCE
#     This file is free software; you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation; either version 2, or (at your option)
#     any later version.
#
#     This file is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have a several hundred copies of of the GNU General Public
#     License on your hard drive.  If not, install Linux, read
#     http://www.gnu.org/copyleft/gpl.html or write to the Free Software
#     Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

__all__ = ['unwrap']

import re

def unwrap(text):
    ''' unwrap (text : string) -> string
        A function that makes every paragraph in a text into a single long line
        so that the text will look right in a "word wrapping" environment
        (e.g. a word processor, HTML text box or a Palm Doc document). '''
    return paragraph.sub(unwrap_para, text)

def regex(s):
    ''' Compile a regex using a "little language" of symbolic names. '''
    for name, expr in names.items():
        s = s.replace(name, expr)
    return re.compile(s, re.DOTALL | re.MULTILINE | re.VERBOSE)

names = {'space':    r'[ \t]',
         'text':     r'[^ \t\n] [^\n]*',
         'newline':  r'\n'
     }

paragraph = regex('''
  ^ ( space+ ) ( text (?: newline text )+ ) $               # indented
| ^ ( space* newline | ^) ( text (?: newline text )+ ) $    # blank-line seperated
''')

whitespace = re.compile(r'\s+', re.DOTALL)

def unwrap_para(match):
    if match.group(3) is None:
        return match.group(1) + whitespace.sub(' ', match.group(2))
    else:
        return match.group(3) + whitespace.sub(' ', match.group(4))

#end
