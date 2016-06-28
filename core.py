import os, os.path, re
from . import utils

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
    if input[0] in utils.STRING_DELIMITERS and input[-1] == input[0]:
        return 'string'
    else:
        return 'statement'

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

    while input and utils.is_wrapped(input, '('): input = input[1:-1] # Remove wrapping parens

    if not input: return []

    # Handle destructuring
    equals = utils.find_all_not_in_parens_or_strings(input, {'re':r'(?<!=)=(?!=)'})
    destruct_ranges = []
    for equal in equals:
        if input[equal+1] == '>': continue # Arrow function, not assignment
        str_remaining = input[equal + 1 :].lstrip()
        if not str_remaining.startswith('{'): continue
        # Found `= {`
        parens = utils.find_matching_parens(input, '{', '}', equal + 1)
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
    if input and utils.is_wrapped(input, '{['):
        _flowtype_enabled = False
        input = input[1:-1]
    elif re.match(r'^{.+}\s*:\s*[^\s\(\)\[\]\{\}+*/&\|=,:~-]+', input):
        _flowtype_enabled = False
        colon = input.rfind(':')
        input = input[:colon].strip()[1:-1]

    input_split = []
    params = []

    split_points = []
    for delim in utils.PARAM_DELIMITERS:
        points = utils.find_all_not_in_parens_or_strings(input, delim)
        points = [
            {'pos': p, 'len': delim.get('len') or len(delim['str'])}
            for p in points
        ]
        split_points.extend(points)

    split_points = sorted(split_points, key = lambda x: x['pos'])

    is_single_param = not split_points

    if is_single_param: # End recursion
        if '=>' in input or 'function' in input: return [] # Handle es6 arrow function edge case `(x) => {...}`
        colon_pos = utils.find_all_not_in_parens_or_strings(input, ':')
        if _flowtype_enabled:
            # Flowtype annotations: Remove object value `foo: Number` => `foo`
            if colon_pos:
                input = input[ : colon_pos[0]].rstrip()
        else:
            # Es6 destructuring: Remove object key `foo: bar` => `bar`
            if colon_pos:
                input = input[colon_pos[0] + 1 : ].rstrip()
        # Remove `foo as bar`
        matches = re.match(r'(?<![^\s\(\)\[\]\{\}+*/&\|=<>,:~-])as\s+(.+)$', input)
        if matches:
            input = matches.group(1)
        param = clean_param(input)
        return filter_params([{"name": param, "type": get_param_type(param)}])

    for i in range(len(split_points)):
        start = i > 0 and split_points[i - 1]['pos'] + split_points[i - 1]['len'] or 0
        end = split_points[i]['pos']
        input_split.append(input[start:end])
    if split_points: input_split.append(input[split_points[-1]['pos'] + split_points[-1]['len'] : ])

    to_strip = utils.PARAM_DELIMITERS_STRIP + ' \t'
    for param in input_split:
        param = param.strip(to_strip)
        if not param: continue
        params.extend(parse_params(param, _flowtype_enabled))

    return filter_params(params)

def clean_line(input):
    "Clean whole line of unnecessary stuff"
    input = input.strip()

    # Remove trailing comments

    point = utils.find_not_in_string(input, '//')
    if point != -1:
        input = input[:point].rstrip()
    point = utils.find_not_in_string(input, '#')
    if point != -1:
        input = input[:point].rstrip()

    # Remove wrapping parens
    while input and utils.is_wrapped(input): input = input[1:-1]

    if not input: return input

    # Remove semicolons and take first statement
    input = input.strip(';').split(';')[0].strip()

    # Remove wrapping parens again
    while input and utils.is_wrapped(input): input = input[1:-1]

    # In case of import line, remove the `from ...` part to make things easier
    matches = re.match(r'^(\s*import\s+.+)\s+from', input)
    if matches:
        input = matches.group(1)

    # In case of coffeescript's `for ... in` remove `in...`
    matches = re.match(r'^(\s*for\s+.+)\s+in\s*.+$', input)
    if matches:
      input = matches.group(1)

    return input

def clean_param(input):
    "Clean a single param"

    input = input.strip(' \t;')

    # Remove coffee's trailing if, unless and for
    if_pos = utils.find_not_in_string(input, {'re':'\sif\s'})
    if if_pos != -1:
        input = input[:if_pos].strip()
    unless_pos = utils.find_not_in_string(input, {'re': '\sunless\s'})
    if unless_pos != -1:
        input = input[:unless_pos].strip()
    for_pos = utils.find_not_in_string(input, {'re': '\sfor\s'})
    if for_pos != -1:
        input = input[:for_pos].strip()

    # Remove wrapping parens
    while input and utils.is_wrapped(input): input = input[1:-1]

    # Remove default value: `foo = 123` => `foo`
    equal_pos = utils.find_not_in_string(input, '=')
    if equal_pos != -1:
        input = input[:equal_pos].strip()

    if not input: return input

    # Remove wrapping parens
    while input and utils.is_wrapped(input): input = input[1:-1]

    input = input.strip(' \t;?')

    # Remove splats
    if input.startswith('...'):
        input = input[3:]

    # Cover up unbalanced parenthesis produced by parse errors
    for chars in [('(',')'), ('[',']'), ('{','}')]:
        opening_parens = utils.find_all_not_in_strings(input, chars[0])
        closing_parens = utils.find_all_not_in_strings(input, chars[1])
        if len(opening_parens) > len(closing_parens):
            if opening_parens[0] == 0: input = input[1:]
            else: input = input[ : opening_parens[0]]
        elif len(opening_parens) < len(closing_parens):
            if closing_parens[-1] == len(input) - 1: input = input[:-1]
            else: input = input[ : closing_parens[-1]]

    return input

def clean_identifier(input):
    "Clean the log identifier"

    input = input.strip(' \t;+<>-')


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
        and i['name'] not in['true', 'false', 'null', 'undefined'] \
        and not i['name'].startswith('.') \
        and not i['name'].endswith('.') \
        and not i['name'].replace('.', '').isdigit():
            unique_names.add(i['name'])
            filtered.append(i)

    return filtered

def create_log_statement(input, alt_identifier, take_inner, flowtype_enabled):
    """
    Return the final log statement to be inserted.
    take_inner indicates wether we'er biased to inspecting the inner statement (towards the right)
    or the outer statement (toward the left).
    eg `var a = fn(function(a, b) {` => (`var a` vs ` `function(a, b) {`)


    Simple assignments:
    (simply log variable) (strategy simple_var)

    >>> create_log_statement('var foo = 1', 'alt', True, True)
    "console.log('foo', foo)"

    >>> create_log_statement('var obj = {a: 1}', 'alt', True, True)
    "console.log('obj', obj)"

    >>> create_log_statement('var obj = getObj(1, 2)', 'alt', True, True)
    "console.log('obj', obj)"

    >>> create_log_statement('obj = getObj(1, 2)', 'alt', True, False) # coffee
    "console.log('obj', obj)"

    >>> create_log_statement('obj = getObj 1, 2', 'alt', True, False) # coffee
    "console.log('obj', obj)"


    Simple assignments + interesting values:
    (take value, split apart) (strategy value)

    >>> create_log_statement('var foo = a + b', 'alt', True, True)
    "console.log('foo', 'a:', a, 'b:', b)"

    >>> create_log_statement('var foo = fn(1, 2) + b', 'alt', True, True)
    "console.log('foo', 'fn(1, 2):', fn(1, 2), 'b:', b)"

    >>> create_log_statement('foo = fn(1, 2) + b', 'alt', True, False) # coffee
    "console.log('foo', 'fn(1, 2):', fn(1, 2), 'b:', b)"


    Complex assignments:
    (take assignee, split apart) (strategy simple_var)

    >>> create_log_statement('var {a, b} = getObj(1, 2)', 'alt', True, True) # Switch to id + break apart
    "console.log('{a, b}', 'a:', a, 'b:', b)"

    >>> create_log_statement('{a, b} = getObj(1, 2)', 'alt', True, False) # coffee
    "console.log('{a, b}', 'a:', a, 'b:', b)"

    >>> create_log_statement('var {a:c, b:d} = getObj(1, 2)', 'alt', True, True)
    "console.log('{a:c, b:d}', 'c:', c, 'd:', d)"

    >>> create_log_statement('var [a, b] = getArr(1, 2)', 'alt', True, True)
    "console.log('[a, b]', 'a:', a, 'b:', b)"

    >>> create_log_statement('var [a, b, ...rest] = getArr(1, 2)', 'alt', True, True)
    "console.log('[a, b, ...rest]', 'a:', a, 'b:', b, 'rest:', rest)"

    >>> create_log_statement('[a, b, ...rest] = getArr(1, 2)', 'alt', True, False) # coffee
    "console.log('[a, b, ...rest]', 'a:', a, 'b:', b, 'rest:', rest)"

    >>> create_log_statement('let {[a]: b} = getObj()', 'alt', True, True)
    "console.log('{[a]: b}', 'b:', b)"


    Simple assignments + flowtype
    (simply log variable) (strategy simple_var)

    >>> create_log_statement('var obj:{a:String, b:Number} = getObj(1, 2)', 'alt', True, True)
    "console.log('obj', obj)"

    >>> create_log_statement('var obj:{a:String, b:Number} = {a:"foo", b:1}', 'alt', True, True)
    "console.log('obj', obj)"


    Return
    (take value, split apart) (strategy value)

    >>> create_log_statement('return 1', 'alt', True, True)
    "console.log('return')"

    >>> create_log_statement('return {a:1, b:2}', 'alt', True, True)
    "console.log('return')"

    >>> create_log_statement('return getObj(1, 2)', 'alt', True, True)
    "console.log('return', 'getObj(1, 2):', getObj(1, 2))"

    >>> create_log_statement('return a + b', 'alt', True, True)
    "console.log('return', 'a:', a, 'b:', b)"

    >>> create_log_statement('return fn(1, 2) + b', 'alt', True, True)
    "console.log('return', 'fn(1, 2):', fn(1, 2), 'b:', b)"


    If (same as Return but more explicit)
    (take value, split apart, log explicitly) (strategy value + explicit)

    >>> create_log_statement('if(a)', 'alt', True, True)
    "console.log('if', 'a:', a)"

    >>> create_log_statement('if(a) {', 'alt', True, True)
    "console.log('if', 'a:', a)"

    >>> create_log_statement('} else if(a) {', 'alt', True, True)
    "console.log('if', 'a:', a)"

    >>> create_log_statement('if(getObj(1, 2))', 'alt', True, True)
    "console.log('if', 'getObj(1, 2):', getObj(1, 2))"

    >>> create_log_statement('if (a + b)', 'alt', True, True)
    "console.log('if', 'a:', a, 'b:', b)"

    >>> create_log_statement('if(fn(1, 2) + b)', 'alt', True, True)
    "console.log('if', 'fn(1, 2):', fn(1, 2), 'b:', b)"


    Function calls
    (take params, split apart) (strategy params)

    >>> create_log_statement('fn(a, b)', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a, {b:d, c:f})', 'alt', True, True)
    "console.log('fn', 'a:', a, 'd:', d, 'f:', f)"

    >>> create_log_statement('fn a, b', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn a, {b:c} ', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a, 'c:', c)"

    >>> create_log_statement('fn a, fn(b, c) ', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a, 'fn(b, c):', fn(b, c))"


    Function definitions
    (take params, split apart) (strategy params)

    >>> create_log_statement('function fn(a, b) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('var fn = function(a, b) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a, b) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn = (a, b) =>', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn = (a, b) ->', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn: (a, b) ->', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn: ->', 'alt', True, False) # coffee
    "console.log('fn')"

    >>> create_log_statement('fn: =>', 'alt', True, False) # coffee
    "console.log('fn')"

    >>> create_log_statement('fn(a, b): any {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn = (a, b) => {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('function fn({a = 5, b = 10} = {}) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('function fn ({a = 5, b = 10} = {}) ->', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a: Number, b: Number = 25) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn({a: value1, b: value2} = {}) {', 'alt', True, True)
    "console.log('fn', 'value1:', value1, 'value2:', value2)"

    >>> create_log_statement('fn({a, b = 25}:SomeType = {}) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('export function fn(a, b) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"

    >>> create_log_statement('export default function fn(a, b) {', 'alt', True, True)
    "console.log('fn', 'a:', a, 'b:', b)"



    Callbacks
    (take params, split apart) (strategy params)

    >>> create_log_statement('fn(a, b).then(function(a) {', 'alt', True, True)
    "console.log('alt', 'a:', a)"

    >>> create_log_statement('fn(a, b).then((a) => {', 'alt', True, True)
    "console.log('then', 'a:', a)"

    >>> create_log_statement('fn(a, b).then(a => { 1 })', 'alt', True, True)
    "console.log('then')"

    >>> create_log_statement('success: function(a) {', 'alt', True, True)
    "console.log('success', 'a:', a)"

    >>> create_log_statement('success: (a, b) ->', 'alt', True, False) # coffee
    "console.log('success', 'a:', a, 'b:', b)"

    >>> create_log_statement('success: (a, b) => {', 'alt', True, False) # coffee
    "console.log('success', 'a:', a, 'b:', b)"

    >>> create_log_statement('fn(a => {', 'alt', True, True)
    "console.log('fn', 'a:', a)"

    >>> create_log_statement('fn (a) ->', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a)"

    >>> create_log_statement('fn ({a}) ->', 'alt', True, False) # coffee
    "console.log('fn', 'a:', a)"

    >>> create_log_statement('success: ({a = 5, b = 10}) => {', 'alt', True, True)
    "console.log('success', 'a:', a, 'b:', b)"
    """

    def _parse_assignee(input):
        if not input: return None
        equals = utils.find_all_not_in_parens_or_strings(input, {'re': '(?<![<>=])=(?!=)'})
        colons = utils.find_all_not_in_parens_or_strings(input, ':')
        if not equals and not colons: return None

        # Split assignee and assignment
        if equals:
            input = input[:equals[0]].rstrip()

        # Handle flowtype `var foo:{a: Number}` => `var foo`
        # Also handles simple object keys `success: function() {`
        if colons:
            input = input[:colons[0]].rstrip()

        if input.startswith('var '): input = input[3:].lstrip()
        elif input.startswith('let '): input = input[3:].lstrip()
        elif input.startswith('const '): input = input[5:].lstrip()

        return input

    def _parse_function_name(input):
        "Return the function name at the end of the string"
        if not input: return None
        name = None
        extra = '' # Append this to what we find with regex
        while input[-1] in ')}]':
            char_opening = {')': '(', ']': '[', '}': '{'}[input[-1]]
            parens = utils.rfind_matching_parens(input, char_opening, input[-1])
            if not parens or parens[1] != len(input) - 1: return None # Unbalanced parens in front of fn call
            extra = input[parens[0] : parens[1] + 1] + extra
            input = input[:parens[0]]

        input = input.rstrip('-=>:()[]{} \t')
        matches = re.findall(r'([^\s\(\)\[\]\{\}+*/&\|=<>,:~-]+)$', input)
        if matches and len(matches):
            name = matches[0].strip('.') + extra
        else:
            name = extra

        return name not in ['function'] and name or None

    def parse_strategy_simple_var(input, take_inner):
        while input and utils.is_wrapped(input): input = input[1:-1]

        is_assignment = utils.find_all_not_in_parens_or_strings(input, {'re': r'(?<![<>])=(?!\>)'})
        is_return = re.match(r'^\s*return', input)
        is_import = re.match(r'^\s*import', input)
        is_for = re.match(r'^\s*for\(', input)
        is_export = re.match(r'^\s*export(?!\s+function)', input)
        is_function = re.match(r'^.*((function\s*([^\s\(\)\[\]\{\}+*/&\|=<>,:~-]+)?\s*\()|(\=\>)|(\-\>))', input)

        # Well this is just horrible but coffeescript clashes with es6 here pretty badly so...
        # Make sure `foo: ->` is parsed as an assignment rather than a function
        is_function_without_parens_assignment = re.match(r'([^\s\(\)\[\]\{\}+*/&\|=<>,:~-]+)\s*:\s*[^\(\)]*$', input)

        if not is_assignment \
        and not is_function_without_parens_assignment \
        and not is_return \
        and not is_export \
        and not is_import \
        or (is_function and take_inner and not is_function_without_parens_assignment):
            return None

        strat = {}

        if is_return:
            strat['identifier_str'] = 'return'
            input = input[input.find('return') + 6 :].lstrip()
            if input.startswith('if '): input = input[3:].lstrip()
            elif input.startswith('unless '): input = input[7:].lstrip()
        elif is_import:
            strat['identifier_str'] = 'import'
            input = input[input.find('import') + 6 :].lstrip()
        elif is_export:
            strat['identifier_str'] = 'export'
            input = input[input.find('export') + 6 :].lstrip()
        elif is_for:
            strat['identifier_str'] = 'for'
            input = input[input.find('for') + 4 : input.find(';')].strip()

        # Find first part of assignment `var foo:{a: Number} = {...}` => `var foo:{a: Number}`
        input = _parse_assignee(input) or input

        if 'identifier_str' not in strat: strat['identifier_str'] = input
        if not is_function_without_parens_assignment:
            strat['param_str'] = input

        return strat

    def parse_strategy_value(input, take_inner):
        # Like simple_var but value more interesting than identifier
        strat = parse_strategy_simple_var(input, take_inner)
        if not strat: return None

        # Find second part of assignment `var foo:{a: Number} = {...}` => `{...}`
        equals = utils.find_all_not_in_parens_or_strings(input, {'re': r'(?<![<>])=(?!\>)'})
        if not equals: return None
        input = input[equals[0] + 1 : ].lstrip()


        # Look for object/array value
        if utils.is_wrapped(input):
            return strat

        ii_found_in_assignment = [
            i for i in
            [utils.find_not_in_string(input, i) for i in utils.INTERESTING_INDICATORS]
            if i != -1
        ]

        ii_found_in_assignee = [
            i for i in
            [utils.find_not_in_string(strat['identifier_str'], i) for i in utils.INTERESTING_INDICATORS]
            if i != -1
        ]

        if ii_found_in_assignment and not ii_found_in_assignee:
            if not take_inner:
                # Remove lambdas
                fn = utils.find_all_not_in_parens_or_strings(input, 'function')
                if fn:
                    input = input[:fn[0]]
                else:
                    arrows = utils.find_all_not_in_parens_or_strings(input, '=>')
                    arrows.extend(utils.find_all_not_in_parens_or_strings(input, '->'))
                    parens = utils.rfind_matching_parens(input)
                    if arrows and parens:
                        input = input[:parens[0]]
            strat['param_str'] = input
            return strat

        return None

    def parse_strategy_params_coffee(input, take_inner):
        strat = {}
        # Find stuff like `foo bar` and assume it's a function call
        matches = re.findall(r'^(else if|[^\s\(\)\[\]\{\}+*/&\|=<>,:~-]+)\s+([^\s=<>\(\)\[\]\{\}]+.*)\s*$', input)
        if not matches or not len(matches): return None
        if matches[0][0] in ['export', 'default', 'return', 'new', 'import', 'export', 'function']: return None

        strat['identifier_str'] = matches[0][0].strip()
        strat['param_str'] = matches[0][1].strip()

        if strat['identifier_str'] in ['var', 'let', 'const', 'function']: return None

        return strat


    def parse_strategy_params(input, take_inner):
        strat = {'param_str': ''}
        # Look for fat arrow without parens first
        if take_inner:
            arrows = utils.find_all_not_in_parens_or_strings(input, '=>')
            arrows.extend(utils.find_all_not_in_parens_or_strings(input, '->'))
            if arrows:
                # Get variable without parens before arrow (`x => ...`)
                matches = re.search(r'([^\s\(\)\[\]\{\}+*/&\|=<>,:~-]+)\s*\(?(\(\s*\))?\s*$', input[:arrows[-1]])
                if matches:
                    strat['param_str'] = matches.group(1)
                    input = input[:matches.start(0)].rstrip()

        # Look for last matching parens and use that
        if not strat.get('param_str'):
            if take_inner:
                parens = utils.rfind_matching_parens(input, '(', ')')
            else:
                parens = utils.find_matching_parens(input, '(', ')')
            if parens:
                # If take_inner is False then taking last matching parens is wrong
                # if not take_inner and parens[0] != utils.find_not_in_string(input, '('): return None
                strat['param_str'] = input[parens[0] + 1 : parens[1]]
                input = input[:parens[0]].rstrip()
            else:
                return None

        # Find identifier
        strat['identifier_str'] = _parse_assignee(input) or _parse_function_name(input)

        return strat

    def parse_strategy_fallback(input, take_inner):
        return {
            'param_str': input
        }


    strat_value = None
    strat_simple_var = None
    strat_params = None
    strat_coffee_return = None
    params = []
    input = clean_line(input)

    strat_value = parse_strategy_value(input, take_inner)
    strat_simple_var = parse_strategy_simple_var(input, take_inner)
    if not strat_value and not strat_simple_var:
        strat_params = parse_strategy_params_coffee(input, take_inner) or parse_strategy_params(input, take_inner)
        strat_coffee_return = parse_strategy_fallback(input, take_inner)

    strat = strat_value or strat_simple_var or strat_params or strat_coffee_return

    if strat:
        params = parse_params(strat.get('param_str', ''), flowtype_enabled)

    # If assignment with only 1 param, no need to expand it, switch to simple_var
    if len(params) == 1 and strat_simple_var and strat is not strat_simple_var:
        strat = strat_simple_var
        params = parse_params(strat.get('param_str', ''))

    strat = strat or {
        'display_key': True
    }

    for param in params: param['display_key'] = True
    if len(params) == 1 and params[0]['name'] == strat.get('identifier_str'):
        params[0]['display_key'] = False

    args = []
    identifier = utils.shorten(clean_identifier(strat.get('identifier_str') or alt_identifier)).replace("'", "\\'")
    args.append("'%s'" % identifier)
    args.extend([
        (p['type'] == 'string' or not p['display_key']) \
            and p['name']
            or "'" + utils.shorten(p['name']).replace("'", "\\'") + ":', " + p['name'] # 'name': name
        for p in params
    ])

    return "console.log(%s)" % (', '.join(args))

def cycle_log_types(view, edit, line_region, line, direction):
    """
    Parses the current `console.xxx` from the given line and replaces xxx with the
    next log method.
    """
    current_type = None

    matches = re.match(r'^\s*console\.(\w+)', line)
    if not matches: return

    current_type = matches.group(1)
    if current_type not in utils.LOG_TYPES: return

    inc = direction == 'down' and 1 or -1
    next_type = utils.LOG_TYPES[(utils.LOG_TYPES.index(current_type) + inc) % len(utils.LOG_TYPES)]
    new_line = line.replace('console.' + current_type, 'console.' + next_type)

    view.replace(edit, line_region, new_line)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
