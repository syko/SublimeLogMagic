import re
from . import core
from . import utils

def log_statement_command(view, edit, direction = 'down'):
    """
    Insert the log statement after or before the current line or cycles the log statement type
    if the cursor is on a log statement line.
    """

    (line_region, line) = utils.get_current_line(view)

    flowtype_enabled = 'source.js' in view.scope_name(line_region.a)

    if utils.is_log_statement(line):
        return core.cycle_log_types(view, edit, line_region, line, direction)

    line_nr, col_nr = view.rowcol(line_region.a)
    alt_identifier = "L%d" % (line_nr + 3)

    statement = core.create_log_statement(line, alt_identifier, direction == 'down', flowtype_enabled)
    insert_log_statement(view, edit, line_region, direction, statement)

def insert_log_statement(view, edit, line_region, direction, statement):
    import sublime
    if direction == 'down':
        insert_point = line_region.b
        newline_tmpl = "\n%s"
        indentline_region = line_region # Inspect indent from current line
    else:
        insert_point = line_region.a
        newline_tmpl = "%s\n"
        indentline_region = view.line(line_region.a - 1) # Inspect indent from previous line

    def find_next_line_with_content(region):
        "Find the last line that has non-whitespace characters"
        while 0 < region.a and region.b < view.size() and view.classify(region.a) is sublime.CLASS_EMPTY_LINE:
            if direction == 'down':
                region = view.line(region.a - 1)
            else:
                region = view.line(region.b + 1)
        return region

    def get_indent_of_line(region):
        "Return the indentation of the line marked by region"
        line = view.substr(region)
        matches = re.findall(r'^(\s*)[^\s]', line)
        return matches and len(matches) and matches[0] or ''


    indent_str = get_indent_of_line(line_region)

    if direction == 'down': # Add extra indent if opening new block
        indentline_region = find_next_line_with_content(indentline_region)
        indent_line = view.substr(indentline_region).strip()
        should_indent = [True for i in utils.INDENT_ENDINGS if indent_line.endswith(i)] \
            and [True for i in utils.INDENT_IDENTIFIERS if indent_line.startswith(i)]
        indent_line.lstrip('{}[]() \t')
        if should_indent:
            indent_str += len(indent_str) and indent_str[0] == '\t' and '\t' or '  ' # Umm.. just assume 2 spaces if using spaces

    statement = indent_str + statement
    statement = newline_tmpl % statement

    view.insert(edit, insert_point, statement)
    view.sel().clear()

    # Move cursor to end of log statement
    selection_start = insert_point + len(statement) - 1
    view.sel().add(sublime.Region(selection_start))

import sublime, sublime_plugin

class LogMagicDownCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        log_statement_command(self.view, edit, 'down')

class LogMagicUpCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        log_statement_command(self.view, edit, 'up')

