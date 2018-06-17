import re

LOG_TYPES = ['log', 'info', 'warn', 'error']
STRING_DELIMITERS =['"', "'", '`']
PARAM_DELIMITERS = [
    {'str': ','},
    {'str': '+'},
    {'str': '-'},
    {'str': '*'},
    {'str': '/'},
    {'str': '-'},
    {'str': '&&'},
    {'str': '||'},
    {'str': '<'},
    {'str': '<='},
    {'str': '>='},
    {'str': '?='},
    {'re': r'===', 'len': 3},
    {'re': r'!==', 'len': 3},
    {'re': r'==', 'len': 2},
    {'re': r'(?<!=)>', 'len': 1},
    {'re': r'(?<=\s)and(?=\s)', 'len': 3},
    {'re': r'(?<=\s)or(?=\s)', 'len': 2},
    {'re': r'(?<=\s)is(?=\s)', 'len': 2},
    {'re': r'(?<=\s)isnt(?=\s)', 'len': 4},
    {'re': r'(?<=\s)in(?=\s)', 'len': 2}
]
INTERESTING_INDICATORS = [
    ',',
    '+',
    '-',
    '/',
    '*',
    '&',
    '|',
    '%',
    {'re': r'(?<=\s)in(?=\s)'},
    {'re': r'(?<=\s)and(?=\s)'},
    {'re': r'(?<=\s)or(?=\s)'},
    {'re': r'(?<=\s)is(?=\s)'},
    {'re': r'(?<=\s)isnt(?=\s)'}
]
PARAM_DELIMITERS_STRIP = ''.join([',','+','-','*','/','-','&&','||','>','<','=='])
INDENT_ENDINGS = ['{', '=', ':', '->', '=>']

def infinite(max_iterations = 200):
    "A generator for use in place of `while True`. Comes with friendly infinite loop protection."
    i = 0
    while i < max_iterations:
        yield True
        i += 1
    raise Exception("Infinite loop protection kicked in (i=%d). Fix your crappy loop!" % i)

def get_current_lines(view):
    "Returns the first highlighted line region and line contents"
    for s in view.sel():
        line_region = view.line(s)
        line = view.substr(line_region)
        yield (line_region, line)

def get_setting(name, default = None):
    try:
        import sublime
        settings = sublime.load_settings('LogMagic.sublime-settings')
    except:
        return default
    return settings.get(name, default)

def find_strings(input):
    """
    Find string literals in string

    >>> find_strings('"foo" + `bar` + 123, \\\\\\'foo \\\\"b\\\\\\\\"ar\\\\\\'')
    [(0, 4), (8, 12), (32, 37)]
    >>> find_strings('boo\\\\"foo"bar')
    [(8, 12)]
    """

    string_ranges = []

    def count_backslashes(input, from_pos):
        num_backslashes = 0
        i = from_pos
        while i >= 0:
            if input[i] == '\\':
                num_backslashes += 1
                i -= 1
            else:
                break
        return num_backslashes

    for delim in STRING_DELIMITERS:
        start = -1
        for i in infinite():
            first = input.find(delim, start + 1)
            if first == -1: break # to next delim
            start = first + 1
            if count_backslashes(input, first - 1) % 2 != 0: continue # Esacped: to next delim
            next = first
            for i in infinite():
                next = input.find(delim, next + 1)
                if next == -1: break # to next delim
                if count_backslashes(input, next - 1) % 2 == 0: break # Not escaped: stop looking

            if next == -1: # ??? unmatches quotations
                string_ranges.append((first, len(input)))
                break # to next delim
            start = next
            string_ranges.append((first, next))

    return sorted(string_ranges)

def remove_strings(input):
    """
    Remove all string literals from input

    >>> remove_strings('"foo" + `bar` + 123, \\'foo "b\\\\\\"ar\\'')
    ' +  + 123, '

    >>> remove_strings('closing-delim-not-found\\\\"foo"bar')
    'closing-delim-not-found\\\\"foo'
    """
    string_ranges = find_strings(input)
    for i in reversed(string_ranges):
        input = input[:i[0]] + input[i[1] + 1:]
    return input


def find_not_in_string(input, char, start = 0):
    """
    Return index of next occurence of char in string input that is not inside a string literal

    >>> find_not_in_string('foo = 1', '=')
    4

    >>> find_not_in_string('"foo = 1" == true', '=')
    10

    >>> find_not_in_string('\\'foo = 1\\' == true', '=')
    10

    >>> find_not_in_string('`foo = 1` == true', '=')
    10
    """
    string_ranges = find_strings(input)
    index = start
    for i in infinite():
        if isinstance(char, str):
            index = input.find(char, index)
        elif char.get('str'): # {str:...} obj
            index = input.find(char['str'], index)
        else: # {re:...} obj
            matches = re.search(char['re'], input[index:])
            index = matches and index + matches.start(0) or -1
        if index == -1: return -1
        is_within_string = [True for s in string_ranges if s[0] <= index and s[1] >= index]
        if is_within_string:
            index += 1
            continue # Found char is within string, keep looking
        return index

def find_matching_parens(input, char_opening = '(', char_closing = ')', start = 0, _recursion = False):
    """
    Return a tuple of the indexes of the first matching parenthesis in the string.
    _recursion is a hack to make sure the top-level call will skip over unopened closing parens.

    >>> find_matching_parens('a(b)', '(', ')')
    (1, 3)

    >>> find_matching_parens('a(b)(c)', '(', ')')
    (1, 3)

    >>> find_matching_parens('ab', '(', ')')

    >>> find_matching_parens('a(b', '(', ')')

    >>> find_matching_parens('a((b', '(', ')')

    >>> find_matching_parens('a((b)', '(', ')')
    (2, 4)

    >>> find_matching_parens('a((b))', '(', ')')
    (1, 5)

    >>> find_matching_parens('a(b))', '(', ')')
    (1, 3)

    >>> find_matching_parens('a"("(b))', '(', ')')
    (4, 6)

    >>> find_matching_parens('a")"(b))', '(', ')')
    (4, 6)

    >>> find_matching_parens('a(b`)`)', '(', ')')
    (1, 6)
    """
    first_inner_parens = None
    opening = find_not_in_string(input, char_opening, start)
    closing = find_not_in_string(input, char_closing, start)
    if opening == -1 or (_recursion and closing < opening): return None
    start = opening + 1
    for i in infinite():
        inner_parens = find_matching_parens(input, char_opening, char_closing, start, True)
        if not first_inner_parens: first_inner_parens = inner_parens # Store for returning if current level is unbalanced
        if inner_parens: start = inner_parens[1] + 1
        next_opening = find_not_in_string(input, char_opening, start)
        next_closing = find_not_in_string(input, char_closing, start)
        if next_closing != -1 and (next_opening == -1 or next_opening > next_closing): # Current level closing found
            return (opening, next_closing)
        elif not inner_parens: # Not inner parens but found '(' :(
            return first_inner_parens # Return the first one that matched after this

def rfind_matching_parens(input, char_opening = '(', char_closing = ')', end = -1):
    """
    Return a tuple of the indexes of the last matching parenthesis in the string

    >>> rfind_matching_parens('a(b)', '(', ')')
    (1, 3)

    >>> rfind_matching_parens('a(b)(c)', '(', ')')
    (4, 6)

    >>> rfind_matching_parens('a(b', '(', ')')

    >>> rfind_matching_parens('a((b', '(', ')')

    >>> rfind_matching_parens('a((b)', '(', ')')
    (2, 4)

    >>> rfind_matching_parens('a((b)((c))', '(', ')')
    (5, 9)
    """
    # Suboptimal implementation but I'm lazy :|
    start = 0
    parens = None
    last_parens = None
    for i in infinite():
        parens = find_matching_parens(input, char_opening, char_closing, start)
        if not parens: return last_parens
        if end != -1 and parens[1] >= end: return last_parens
        start = parens[1] + 1
        last_parens = parens

def find_all_matching_parens(input, char_opening = '(', char_closing = ')', start = 0):
    """
    Return a list of tuples of the indexes of all matching parenthesis in the string

    >>> find_all_matching_parens('a(b)', '(', ')')
    [(1, 3)]

    >>> find_all_matching_parens('a(b)(c)', '(', ')')
    [(1, 3), (4, 6)]

    >>> find_all_matching_parens('a(b', '(', ')')
    []

    >>> find_all_matching_parens('a((b', '(', ')')
    []

    >>> find_all_matching_parens('a((b)', '(', ')')
    [(2, 4)]

    >>> find_all_matching_parens('a((b))', '(', ')')
    [(1, 5), (2, 4)]
    """
    all_parens = []
    for i in infinite():
        parens = find_matching_parens(input, char_opening, char_closing, start)
        if not parens: break
        all_parens.append(parens)
        start = parens[0] +     1
    return sorted(all_parens)

def find_all_not_in_strings(input, char, start = 0):
    """Return a list of found character positions that are not in strings.

    >>> find_all_not_in_strings('fo"o,", bar', ',')
    [6]

    >>> find_all_not_in_strings('fo"o,",, bar', ',')
    [6, 7]

    """
    all = []
    next = -1
    for i in infinite():
        next = find_not_in_string(input, char, next + 1)
        if next == -1: return all # Done
        all.append(next)

def find_all_not_in_parens_or_strings(input, char, parens = '([{', start = 0):
    """Return a list of found character positions that are not in strings or parens.

    >>> find_all_not_in_parens_or_strings('foo, bar', ',', '([{')
    [3]

    >>> find_all_not_in_parens_or_strings('{foo:bar} = {=}=', '=', '([{')
    [10, 15]

    >>> find_all_not_in_parens_or_strings('{foo = bar} = {}', '=', '([{')
    [12]
    """
    all_parens = []
    if '(' in parens: all_parens.extend(find_all_matching_parens(input, '(', ')'))
    if '[' in parens: all_parens.extend(find_all_matching_parens(input, '[', ']'))
    if '{' in parens: all_parens.extend(find_all_matching_parens(input, '{', '}'))
    all = []
    next = -1
    for i in infinite():
        next = find_not_in_string(input, char, next + 1)
        if next == -1: return all # Done
        if not len([i for i in all_parens if i[0] < next < i[1]]):
            all.append(next) # char is not within parens

def is_wrapped(input, paren_types = '([{'):
    """
    Return true if input is fully wrapped in {} or []

    >>> is_wrapped('(abc)')
    True

    >>> is_wrapped('abc)')
    False

    >>> is_wrapped('((abc)')
    False

    >>> is_wrapped('[abc]')
    True

    >>> is_wrapped('{abc: foo}')
    True

    >>> is_wrapped('({abc: foo}, 123)')
    True

    >>> is_wrapped('{abc: foo}, 123)')
    False

    """
    if '(' in paren_types:
        parens = find_matching_parens(input, '(', ')')
        if parens and parens[0] == 0 and parens[1] == len(input) - 1: return True
    if '[' in paren_types:
        parens = find_matching_parens(input, '[', ']')
        if parens and parens[0] == 0 and parens[1] == len(input) - 1: return True
    if '{' in paren_types:
        parens = find_matching_parens(input, '{', '}')
        if parens and parens[0] == 0 and parens[1] == len(input) - 1: return True
    return False

def is_log_statement(line):
    return line.strip().startswith('console.')

def shorten(input):
    "Shortens long strings by putting '...' in the middle"
    max_length = get_setting('max_identifier_length', 21)
    if len(input) <= max_length: return input
    return input[ : max_length - 6] + '...' + input[-3:]

if __name__ == "__main__":
    import doctest
    doctest.testmod()