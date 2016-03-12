import os, os.path, re, codecs

LOG_TYPES = ['log', 'info', 'warn', 'error']
STRING_DELIMITERS =['"', "'", '`']
PARAM_DELIMITERS = [',','+','-','*','/','-','&&','||',{'re': r'(?<!=)>'},'<','==']
PARAM_DELIMITERS_STRIP = ''.join([',','+','-','*','/','-','&&','||','>','<','=='])

def infinite(max_iterations = 200):
    "A generator for use in place of `while True`. Comes with friendly infinite loop protection."
    i = 0
    while i < max_iterations:
        yield True
        i += 1
    raise Exception("Infinite loop protection kicked in (i=%d). Fix your crappy loop!" % i)

def get_current_line(view):
    "Returns the first highlighted line region and line contents"
    line_region = view.line(view.sel()[0])
    line = view.substr(line_region)
    return (line_region, line)

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

def get_param_type(input):
    """
    Return the parameter type for a single parameter.

    >>> get_param_type('foo')
    'statement'

    >>> get_param_type('1')
    'statement'

    >>> get_param_type('function() {}')
    'statement'

    >>> get_param_type('"foo"')
    'string'

    >>> get_param_type('\\'foo\\'')
    'string'

    >>> get_param_type('`foo`')
    'string'
    """
    if not input: return ''
    if input[0] in STRING_DELIMITERS and input[-1] == input[0]:
        return 'string'
    else:
        return 'statement'


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

def parse_params(input, _flowtype_enabled = True):
    """
    Revursively parse a string of interesting attributes and split it apart.

    >>> parse_params('foo, bar') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'bar'}]
    True

    >>> parse_params('(foo), bar') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'bar'}]
    True

    >>> parse_params('"somestring", bar') == [{'type': 'string', 'name': '"somestring"'}, {'type': 'statement', 'name': 'bar'}]
    True

    >>> parse_params('foo || bar, bar && buzz || 1, hello') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'bar'}, {'type': 'statement', 'name': 'buzz'}, {'type': 'statement', 'name': 'hello'}]
    True

    >>> parse_params('foo, function() { 1; }') == [{'type': 'statement', 'name': 'foo'}]
    True

    >>> parse_params('foo, (x) => { 1; }') == [{'type': 'statement', 'name': 'foo'}]
    True

    >>> parse_params('foo, (x) => 1') == [{'type': 'statement', 'name': 'foo'}]
    True

    >>> parse_params('foo, someFunc(123)') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'someFunc(123)'}]
    True

    Default values

    >>> parse_params('foo = 1, bar = 2') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'bar'}]
    True

    >>> parse_params('(foo = 1), bar') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'bar'}]
    True

    Es6 destructuring

    >>> parse_params('{foo, bar} = {}') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'bar'}]
    True

    >>> parse_params('[foo, bar]') == [{'type': 'statement', 'name': 'foo'}, {'type': 'statement', 'name': 'bar'}]
    True

    >>> parse_params('[{foo: 1, bar: 2}, buzz]') == [{'type': 'statement', 'name': 'buzz'}]
    True
    """

    input = input.strip()

    while input and is_wrapped(input, '('): input = input[1:-1] # Remove wrapping parens

    if not input: return []

    # Handle destructuring
    equals = find_all_not_in_parens_or_strings(input, '=')
    destruct_ranges = []
    for equal in equals:
        if input[equal+1] == '>': continue # Arrow function, not assignment
        str_remaining = input[equal + 1 :].lstrip()
        if not str_remaining.startswith('{'): continue
        # Found `= {`
        parens = find_matching_parens(input, '{', '}', equal + 1)
        if parens:
            destruct_ranges.append((equal, parens[1] + 1))
        else: # No destructuring end? ... let's remove this crap :|
            destruct_ranges.append((equal, input.find('{', equal) + 1))

    for d_range in reversed(destruct_ranges):
        input = input[:d_range[0]] + input[d_range[1]:]

    input = input.strip()

    # Detect if we can use flowtype or should switch to es6 destructuring
    # in case of `fn(a:Number, b:Number = 25)` we can use flowtype but if there is destructuring involved
    # we have to switch to `fn({a:alias, b:alias2}:SomeFlowType = {})`.
    if input and is_wrapped(input, '{['):
        _flowtype_enabled = False
        input = input[1:-1]
    elif re.match(r'^{.+}\s*:\s*[^\s\(\)\[\]\{\}+*/&\|=,:~-]+', input):
        _flowtype_enabled = False
        colon = input.rfind(':')
        input = input[:colon].strip()[1:-1]

    str_split = []
    params = []

    split_points = []
    for i in PARAM_DELIMITERS:
        split_points.extend(find_all_not_in_parens_or_strings(input, i))

    split_points.sort()

    is_single_param = not split_points

    if is_single_param: # End recursion
        if '=>' in input or 'function' in input: return [] # Handle es6 arrow function edge case `(x) => {...}`
        colon_pos = find_not_in_string(input, ':')
        if _flowtype_enabled:
            # Flowtype annotations: Remove object value `foo: Number` => `foo`
            if colon_pos != -1:
                input = input[ : colon_pos].rstrip()
        else:
            # Es6 destructuring: Remove object key `foo: bar` => `bar`
            if colon_pos != -1:
                input = input[colon_pos + 1 : ].rstrip()
        param = clean_param(input)
        return filter_params([{"name": param, "type": get_param_type(param)}])

    for i in range(len(split_points)):
        start = i > 0 and split_points[i - 1] + 1 or 0
        end = split_points[i]
        str_split.append(input[start:end])
    if split_points: str_split.append(input[split_points[-1] + 1 : ])

    to_strip = PARAM_DELIMITERS_STRIP + ' \t'
    for param in str_split:
        param = param.strip(to_strip)
        if not param: continue
        params.extend(parse_params(param, _flowtype_enabled))

    return filter_params(params)



# def is_variable(input):
#     "Return true if input is a simple variable"
#     return re.match('^[^\(\)\[\]\{\}\.,+~$*/~`"\'-]*$', input) is not None

def clean_line(input):
    "Clean whole line of unnecessary stuff"
    input = input.strip()

    # Remove wrapping parens
    while input and is_wrapped(input): input = input[1:-1]

    if not input: return input

    # Remove semicolons and take first statement
    input = input.strip(';').split(';')[0].strip()

    # Remove wrapping parens again
    while input and is_wrapped(input): input = input[1:-1]

    return input

def clean_param(input):
    "Clean a single param"

    input = input.strip(' \t;')

    # Remove wrapping parens
    while input and is_wrapped(input): input = input[1:-1]

    # Remove default value: `foo = 123` => `foo`
    equal_pos = find_not_in_string(input, '=')
    if equal_pos != -1:
        input = input[:equal_pos].strip()

    if not input: return input

    # Remove wrapping parens
    while input and is_wrapped(input): input = input[1:-1]

    input = input.strip(' \t;')

    # Remove splats
    if input.startswith('...'):
        input = input[3:]

    return input

def filter_params(params):
    "Filter out duplicate params and other pointless stuff"

    # Filter duplicates, known constants, numbers and empty/invalid strings
    unique_names = set()
    filtered = []
    for i in params:
        if i['name'] not in unique_names \
        and i['name'].strip('"`\'[](){}') \
        and i['name'].lower() not in['true', 'false', 'null'] \
        and not i['name'].replace('.', '').isdigit():
            unique_names.add(i['name'])
            filtered.append(i)

    return filtered

def shorten(param, max_length = 18):
    "Shortens long strings by putting '...' in the middle"
    if len(param) <= max_length: return param
    return param[ : max_length - 6] + '...' + param[-3:]



def insert_log_statement(view, edit, line_region, direction, statement):
    if direction == 'down':
        insert_point = line_region.b
        newline_tmpl = "\n%s"
        indentline_region = line_region # Inspect indent from current line
    else:
        insert_point = line_region.a
        newline_tmpl = "%s\n"
        indentline_region = view.line(line_region.a - 1) # Inspect indent from previous line

    def find_last_line_with_content(region):
        "Find the last line that has non-whitespace characters"
        while region.a > 0 and not view.substr(region).strip():
            region = view.line(region.a - 1)
        return region

    def get_indent_of_line(region):
        "Return the indentation of the line marked by region"
        line = view.substr(region)
        matches = re.findall(r'^(\s*)[^\s]', line)
        return matches and len(matches) and matches[0] or ''


    indentline_region = find_last_line_with_content(indentline_region)
    indent_str = get_indent_of_line(indentline_region)

    should_indent = len(re.findall(r'(:|=|{)\s*$', view.substr(indentline_region))) # Last line ends with :, = or {
    if should_indent:
        indent_str += len(indent_str) and indent_str[0] == '\t' and '\t' or '  ' # Umm.. just assume 2 spaces if using spaces

    statement = indent_str + statement
    statement = newline_tmpl % statement

    view.insert(edit, insert_point, statement)
    view.sel().clear()

    # Move cursor to end of log statement
    selection_start = insert_point + len(statement) - 1
    view.sel().add(sublime.Region(selection_start))

def create_log_statement(input, alt_identifier, take_inner):
    """
    Return the final log statement to be inserted.
    take_inner indicates wether we'er biased to inspecting the inner statement (towards the right)
    or the outer statement (toward the left).
    eg `var a = fn(function(a, b) {` => (`var a` vs ` `function(a, b) {`)


    Simple assignments:
    (simply log variable) (strategy simple_var)

    >>> create_log_statement('var foo = 1', 'alt', True)
    "console.log('foo', foo)"

    >>> create_log_statement('var obj = {a: 1}', 'alt', True)
    "console.log('obj', obj)"

    >>> create_log_statement('var obj = getObj(1, 2)', 'alt', True)
    "console.log('obj', obj)"


    Simple assignments + interesting values:
    (take value, split apart) (strategy value)

    >>> create_log_statement('var foo = a + b', 'alt', True)
    "console.log('foo', 'a:', a, 'b:', b)"

    >>> create_log_statement('var foo = fn(1, 2) + b', 'alt', True)
    "console.log('foo', 'fn(1, 2):', fn(1, 2), 'b:', b)"


    Complex assignments:
    (take assignee, split apart) (strategy simple_var)

    >>> create_log_statement('var {a, b} = getObj(1, 2)', 'alt', True) # Switch to id + break apart,
    "console.log('{a, b}', 'a:', a, 'b:', b)"

    >>> create_log_statement('var {a:c, b:d} = getObj(1, 2)', 'alt', True)
    "console.log('{a:c, b:d}', 'c:', c, 'd:', d)"

    >>> create_log_statement('var [a, b] = getArr(1, 2)', 'alt', True)
    "console.log('[a, b]', 'a:', a, 'b:', b)"

    >>> create_log_statement('var [a, b, ...rest] = getArr(1, 2)', 'alt', True)
    "console.log('[a, b, ...rest]', 'a:', a, 'b:', b, 'rest:', rest)"

    >>> create_log_statement('let {[a]: b} = getObj()', 'alt', True)
    "console.log('{[a]: b}', 'b:', b)"


    Simple assignments + flowtype
    (simply log variable) (strategy simple_var)

    >>> create_log_statement('var obj:{a:String, b:Number} = getObj(1, 2)', 'alt', True)
    "console.log('obj', obj)"

    |>>> create_log_statement('var obj:{a:String, b:Number} = {a:"foo', b:1}", 'alt', True)
    "console.log('obj', obj)"


    Return
    (take value, split apart) (strategy value)

    >>> create_log_statement('return 1', 'alt', True)
    "console.log('return')"

    >>> create_log_statement('return {a:1, b:2}', 'alt', True)
    "console.log('return')"

    >>> create_log_statement('return getObj(1, 2)', 'alt', True)
    "console.log('return', 'getObj(1, 2):', getObj(1, 2))"

    >>> create_log_statement('return a + b', 'alt', True)
    "console.log('return', 'a:', a, 'b:', b)"

    >>> create_log_statement('return fn(1, 2) + b', 'alt', True)
    "console.log('return', 'fn(1, 2):', fn(1, 2), 'b:', b)"


    If (same as Return but more explicit)
    (take value, split apart, log explicitly) (strategy value + explicit)

    >>> create_log_statement('if(a)', 'alt', True)
    "console.log('if', 'a:', a)"

    >>> create_log_statement('if(a) {', 'alt', True)
    "console.log('if', 'a:', a)"

    >>> create_log_statement('} else if(a) {', 'alt', True)
    "console.log('if', 'a:', a)"

    >>> create_log_statement('if(getObj(1, 2))', 'alt', True)
    "console.log('if', 'getObj(1, 2):', getObj(1, 2))"

    >>> create_log_statement('if(a + b)', 'alt', True)
    "console.log('if', 'a:', a, 'b:', b)"

    >>> create_log_statement('if(fn(1, 2) + b)', 'alt', True)
    "console.log('if', 'fn(1, 2):', fn(1, 2), 'b:', b)"


    Function calls
    (take params, split apart) (strategy params)

    >>> create_log_statement('fn(a, b)', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a, {b:d, c:f})', 'alt', True)
    "console.log('fn', 'a:', a, 'd:', d, 'f:', f)"


    Function definitions
    (take params, split apart) (strategy params)

    >>> create_log_statement('function fn(a, b) {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('var fn = function(a, b) {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a, b) {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a, b): any {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn = (a, b) => {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('function fn({a = 5, b = 10} = {}) {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a: Number, b: Number = 25) {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn({a: value1, b: value2} = {}) {', 'alt', True)
    "console.log('fn', 'value1:', value1, 'value2:', value2)"

    >>> create_log_statement('fn({a, b = 25}:SomeType = {}) {', 'alt', True)
    "console.log('fn', 'a:', a, 'b:', b)"



    Callbacks
    (take params, split apart) (strategy params)

    >>> create_log_statement('fn(a, b).then(function(a) {', 'alt', True)
    "console.log('alt', 'a:', a)"

    >>> create_log_statement('fn(a, b).then((a) => {', 'alt', True)
    "console.log('alt', 'a:', a)"

    >>> create_log_statement('fn(a, b).then(a => { 1 })', 'alt', True)
    "console.log('alt')"

    >>> create_log_statement('success: function(a) {', 'alt', True)
    "console.log('success', 'a:', a)"

    >>> create_log_statement('success: (a) => {', 'alt', True)
    "console.log('success', 'a:', a)"

    >>> create_log_statement('fn(a => {', 'alt', True)
    "console.log('fn', 'a:', a)"

    >>> create_log_statement('success: ({a = 5, b = 10}) => {', 'alt', True)
    "console.log('success', 'a:', a, 'b:', b)"
    """

    def _parse_assignee(input):
        equals = find_all_not_in_parens_or_strings(input, '=')
        colons = find_all_not_in_parens_or_strings(input, ':')
        if not equals and not colons: return None

        # Split assignee and assignment
        if equals:
            input = input[:equals[0]].rstrip()

        # Handle flowtype `var foo:{a: Number}` => `var foo`
        # Also handles simple object keys `success: function() {`
        if colons:
            input = input[:colons[0]].rstrip()

        if input.startswith('var'): input = input[3:].lstrip()
        elif input.startswith('let'): input = input[3:].lstrip()
        elif input.startswith('const'): input = input[5:].lstrip()

        return input

    def _parse_function_name(input):
        "Return the function name at the end of the string"
        name = None
        extra = '' # Append this to what we find with regex
        while input[-1] in ')}]':
            char_opening = {')': '(', ']': '[', '}': '{'}[input[-1]]
            parens = rfind_matching_parens(input, char_opening, input[-1])
            if not parens or parens[1] != len(input) - 1: return None # Unbalanced parens in front of fn call
            extra = input[parens[0] : parens[1] + 1] + extra
            input = input[:parens[0]]

        input = input.rstrip('=>:()[]{} \t')
        matches = re.findall(r'([^\s\(\)\[\]\{\}+*/&\|=,:~-]+)$', input)
        if matches and len(matches):
            name = matches[0].strip('.') + extra
        else:
            name = extra

        return name not in ['then', 'function'] and name or None

    def parse_strategy_simple_var(input, take_inner):
        while input and is_wrapped(input): input = input[1:-1]

        is_assignment = find_all_not_in_parens_or_strings(input, {'re': r'=(?!\>)'})
        is_return = re.match(r'^\s*return', input)
        is_function = re.match(r'^.*((function\s*([^\s\(\)\[\]\{\}+*/&\|=,:~-]+)?\()|(\=\>))', input)

        if not is_assignment and not is_return or (is_function and take_inner): return None

        strat = {}

        if is_return:
            strat['identifier_str'] = 'return'
            input = input[input.find('return') + 6 :].lstrip()

        # Find first part of assignment `var foo:{a: Number} = {...}` => `var foo:{a: Number}`
        input = _parse_assignee(input) or input

        if 'identifier_str' not in strat: strat['identifier_str'] = input
        strat['param_str'] = input

        return strat

    def parse_strategy_value(input, take_inner):
        # Like simple_var but value more interesting than identifier
        strat = parse_strategy_simple_var(input, take_inner)
        if not strat: return None

        # Find second part of assignment `var foo:{a: Number} = {...}` => `{...}`
        equals = find_all_not_in_parens_or_strings(input, '=')
        if not equals: return None
        input = input[equals[0] + 1 : ].lstrip()


        # Look for object/array value
        if is_wrapped(input):
            return strat

        interesting_indicators = [',', '+', '-', '/', '*', '&', '|', '%']

        ii_found_in_assignment = [
            i for i in
            [find_not_in_string(input, i) for i in interesting_indicators]
            if i != -1
        ]

        ii_found_in_assignee = [
            i for i in
            [find_not_in_string(strat['identifier_str'], i) for i in interesting_indicators]
            if i != -1
        ]

        if ii_found_in_assignment and not ii_found_in_assignee:
            strat['param_str'] = input
            return strat

        return None

    def parse_strategy_params(input, take_inner):
        strat = {}
        # Look for fat arrow without parens first
        if take_inner:
            arrows = find_all_not_in_parens_or_strings(input, '=>')
            if arrows:
                # Get variable without parens before arrow (`x => ...`)
                matches = re.search(r'([^\s\(\)\[\]\{\}+*/&\|=,:~-]+)\s*$', input[:arrows[-1]])
                if matches:
                    strat['param_str'] = matches.group(1)
                    input = input[:matches.start(0)].rstrip()

        # Look for last matching parens and use that
        if not strat.get('param_str'):
            parens = rfind_matching_parens(input, '(', ')')
            if parens:
                # If take_inner is False then taking last matching parens is wrong
                if not take_inner and parens[0] != find_not_in_string(input, '('): return None
                strat['param_str'] = input[parens[0] + 1 : parens[1]]
                input = input[:parens[0]].rstrip()

        if strat.get('param_str') is None: return None

        # Find identifier
        strat['identifier_str'] = _parse_assignee(input) or _parse_function_name(input)

        return strat


    strat_value = None
    strat_simple_var = None
    strat_params = None
    params = []
    input = clean_line(input)

    strat_value = parse_strategy_value(input, take_inner)
    strat_simple_var = parse_strategy_simple_var(input, take_inner)
    if not strat_value and not strat_simple_var:
        strat_params = parse_strategy_params(input, take_inner)


    strat = strat_value or strat_simple_var or strat_params

    if strat:
        params = parse_params(strat['param_str'])

    # If assignment with only 1 param, no need to expand it, switch to simple_var
    if len(params) == 1 and strat_simple_var and strat is not strat_simple_var:
        strat = strat_simple_var
        params = parse_params(strat['param_str'])

    strat = strat or {
        'display_key': True
    }

    for param in params: param['display_key'] = True
    if len(params) == 1 and params[0]['name'] == strat.get('identifier_str'):
        params[0]['display_key'] = False

    args = []
    identifier = strat.get('identifier_str') or alt_identifier
    args.append("'%s'" % identifier)
    args.extend([
        (p['type'] == 'string' or not p['display_key']) \
            and p['name']
            or "'" + shorten(p['name']).replace("'", "\\'") + ":', " + p['name'] # 'name': name
        for p in params
    ])

    return "console.log(%s)" % (', '.join(args))

def is_log_statement(line):
    return True in [line.strip().startswith('console.' + i) for i in LOG_TYPES]

def cycle_log_types(view, edit, line_region, line, direction):
    """
    Parses the current `console.xxx` from the given line and replaces xxx with the
    next log method.
    """
    current_type = None

    matches = re.match(r'^\s*console\.(\w+)', line)
    if not matches: return

    current_type = matches.group(1)
    if current_type not in LOG_TYPES: return

    inc = direction == 'down' and 1 or -1
    next_type = LOG_TYPES[(LOG_TYPES.index(current_type) + inc) % len(LOG_TYPES)]
    new_line = line.replace('console.' + current_type, 'console.' + next_type)

    view.replace(edit, line_region, new_line)


def log_statement_command(view, edit, direction = 'down'):
    """
    Insert the log statement after or before the current line or cycles the log statement type
    if the cursor is on a log statement line.
    """

    (line_region, line) = get_current_line(view)

    if is_log_statement(line):
        return cycle_log_types(view, edit, line_region, line, direction)

    line_nr, col_nr = view.rowcol(line_region.a)
    alt_identifier = "L%d" % (line_nr + 3)

    statement = create_log_statement(line, alt_identifier, direction == 'down')
    insert_log_statement(view, edit, line_region, direction, statement)

if __name__ == "__main__":

    import doctest
    doctest.testmod()

else:

    import sublime, sublime_plugin

    class LogMagicDownCommand(sublime_plugin.TextCommand):
        def run(self, edit):
            log_statement_command(self.view, edit, 'down')

    class LogMagicUpCommand(sublime_plugin.TextCommand):
        def run(self, edit):
            log_statement_command(self.view, edit, 'up')

