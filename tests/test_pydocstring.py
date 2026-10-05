"""Docstring commands on signatures that span lines.
"""
import pytest
from conftest import FakeBuffer
from pydocstring import Docstring, DocstringUnavailable


def test_oneline_goes_below_multiline_signature(vim):
    """Verify :DocstringLine inserts after the line that closes the signature.

    Mutation: treating the (bool, tree) tuple from _is_valid as the test,
    which is always true, so the docstring lands after the first line.
    Oracle: hand-written buffer with the docstring below 'b):'.
    """
    vim.load('def f(a,\n      b):\n    return a\n', 1)
    Docstring().oneline_docstring()
    assert vim.current.buffer == [
        'def f(a,',
        '      b):',
        '    """  """',
        '    return a',
        '',
        ]


def test_oneline_on_unterminated_signature_reports_invalid_syntax(vim):
    """Verify a signature cut off by the buffer's end raises the syntax error.

    Mutation: the buffer generator raising StopIteration, which Python
    turns into RuntimeError('generator raised StopIteration').
    Oracle: the InvalidSyntax message pydocstring._get_sig raises.
    """
    vim.load('def f(a,\n      b', 1)
    with pytest.raises(DocstringUnavailable) as excinfo:
        Docstring().oneline_docstring()
    assert str(excinfo.value) == 'Docstring ERROR: Object does not have valid syntax'
    assert vim.current.buffer == ['def f(a,', '      b']


def test_full_docstring_goes_below_backslash_continued_signature(vim):
    """Verify :Docstring inserts after a signature continued with a backslash.

    Mutation: joining signature lines with '' so the backslash no longer
    ends a line and the signature never parses.
    Oracle: hand-written buffer with the Google docstring below 'b):'.
    """
    vim.load('def f(a, \\\n      b):\n    return a\n', 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer == [
        'def f(a, \\',
        '      b):',
        '    """',
        '',
        '    Args:',
        '        a:',
        '        b:',
        '',
        '    Returns:',
        '        ',
        '',
        '    """',
        '    return a',
        '',
        ]


def test_oneline_goes_below_backslash_continued_signature(vim):
    """Verify :DocstringLine inserts after a backslash-continued signature.

    Mutation: joining signature lines with '' in _get_sig, so the backslash
    no longer ends a line and the scan runs to the buffer's end.
    Oracle: hand-written buffer with the docstring below 'b):'.
    """
    vim.load('def f(a, \\\n      b):\n    return a\n', 1)
    Docstring().oneline_docstring()
    assert vim.current.buffer == [
        'def f(a, \\',
        '      b):',
        '    """  """',
        '    return a',
        '',
        ]


@pytest.mark.parametrize('command', ['full_docstring', 'oneline_docstring'])
def test_one_line_object_is_refused(vim, command):
    """Verify an object whose body is on its signature line gets no docstring.

    Mutation: dropping the unpadded parse in _is_valid, so the scan runs on
    and writes the docstring under the next function, def g.
    Oracle: the buffer as loaded, since any insertion breaks the class.
    """
    source = 'class E(Exception): pass\n\n\ndef g(a):\n    return a\n'
    vim.load(source, 1, {'python_style': 'google'})
    with pytest.raises(DocstringUnavailable) as excinfo:
        getattr(Docstring(), command)()
    assert str(excinfo.value) == 'Docstring ERROR: Object body is on its signature line'
    assert vim.current.buffer == source.split('\n')


def test_raises_section_follows_source_order(vim):
    """Verify the written Raises section lists classes in source order.

    Mutation: sorted() or a set in place of the source-ordered dict anywhere
    between MethodVisitor and the template.
    Oracle: the hand-written order of six unsorted names, which a set
    matches by chance once in 720 runs.
    """
    names = [
        'TypeError',
        'KeyError',
        'OSError',
        'IndexError',
        'EOFError',
        'ArithmeticError',
        ]
    body = ''.join(f'    raise {name}(a)\n' for name in names)
    vim.load(f'def f(a):\n{body}', 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer[6] == '    Raises:'
    assert vim.current.buffer[7:13] == [f'        {name}:' for name in names]


def test_full_docstring_reads_past_unaligned_string_lines(vim):
    """Verify string lines at column 0 inside the body do not end the object.

    Mutation: checking indentation inside an open triple-quoted string, so
    the scan stops at 'Comment' and the cut-off source fails to parse.
    Oracle: hand-written Google docstring for a function that returns.
    """
    source = 'def foo():\n  x = """\nComment\n"""\n  return x\n'
    vim.load(source, 1, {'python_style': 'google', 'vpd_indent': '  '})
    Docstring().full_docstring()
    assert vim.current.buffer == [
        'def foo():',
        '  """',
        '',
        '  Returns:',
        '    ',
        '',
        '  """',
        '  x = """',
        'Comment',
        '"""',
        '  return x',
        '',
        ]


def test_full_docstring_ignores_a_triple_quote_inside_a_string(vim):
    """Verify a quoted triple quote does not pull the next function in.

    Mutation: counting triple quotes per line in place of tokenizing, so
    the quote in q opens a phantom string and def g's b and ValueError
    land in f's docstring.
    Oracle: hand-written Google docstring for f alone.
    """
    source = (
        'def f(a):\n'
        "    q = '\"\"\"'\n"
        '    return q + a\n'
        '\n'
        '\n'
        'def g(b):\n'
        '    raise ValueError\n')
    vim.load(source, 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer[:10] == [
        'def f(a):',
        '    """',
        '',
        '    Args:',
        '        a:',
        '',
        '    Returns:',
        '        ',
        '',
        '    """',
        ]
    assert vim.current.buffer[10:] == source.split('\n')[1:]


@pytest.mark.parametrize(
    ('source', 'row', 'expected'),
    [
        ('class Shape:\n    def area(this, x):\n        return x\n', 2, ['x']),
        (
            'class Maker:\n    @staticmethod\n    def make(a):\n        return a\n',
            3,
            ['a'],
            ),
        (
            ('class Maker:\n    @classmethod\n    def make(klass, a):\n'
             '        return a\n'),
            3,
            ['a'],
            ),
        (
            ('class Shape:\n    def area(self):\n        def helper(item):\n'
             '            return item\n        return helper\n'),
            3,
            ['item'],
            ),
        ('def f(this, a):\n    return a\n', 1, ['this', 'a']),
        (
            ('class A:\n    @staticmethod\n    def g(a):\n        pass\n\n'
             '    def h(this, b):\n        pass\n'),
            6,
            ['b'],
            ),
        (
            ('class A:\n    @staticmethod\n    @deco(\n        1)\n'
             '    def f(a):\n        pass\n'),
            5,
            ['a'],
            ),
        ('class A:\n    @ staticmethod\n    def f(a):\n        pass\n', 3, ['a']),
        ])
def test_method_first_argument_is_dropped_by_context(vim, source, row, expected):
    """Verify only a method's first argument is dropped, whatever its name.

    Mutation: a name-only rule that drops self or cls (lists this),
    ignoring @staticmethod (drops a), treating an enclosing def as a class
    (drops item), letting an earlier sibling's decorator count (keeps this
    for h), or ending the decorator scan at a continuation line or on
    '@ staticmethod' (drops a).
    Oracle: Python binds the first argument of a non-static method in a
    class body, and of nothing else.
    """
    vim.load(source, row, {'python_style': 'rest'})
    Docstring().full_docstring()
    listed = [
        line.split()[1].rstrip(':') for line in vim.current.buffer if ':param' in line
        ]
    assert listed == expected


def test_full_docstring_tolerates_bytes_that_are_not_utf8_below(vim):
    """Verify a surrogate-escaped byte on the line below f does not block f.

    Mutation: letting tokenize's UnicodeEncodeError out of
    BufferReader.tokenize_to, which fails the whole command. Caught on
    Python 3.12+ only: 3.11's tokenizer reads str lines and never
    encodes them, so the error cannot arise there.
    Oracle: hand-written Google docstring for f alone.
    """
    source = 'def f(a):\n    return a\n\n\ns = "caf\udce9"\n'
    vim.load(source, 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer[:10] == [
        'def f(a):',
        '    """',
        '',
        '    Args:',
        '        a:',
        '',
        '    Returns:',
        '        ',
        '',
        '    """',
        ]


def test_full_docstring_reads_a_def_using_non_ascii_names(vim):
    """Verify a name 3.11 tokenizes as ERRORTOKEN does not end tokenizing.

    Mutation: counting every ERRORTOKEN as a tokenize failure in
    BufferReader.tokenize_to, which on 3.11 leaves the statement holding
    a·b open, so the read takes in g and lists c and KeyError. Caught on
    3.11 only, since 3.12+ tokenizes these names as NAME.
    Oracle: ast.parse of the buffer, where f ends on its return line.
    """
    source = (
        'def f(a):\n    x = a·b\n    return x\n\n\n'
        'def g(c):\n    raise KeyError\n')
    vim.load(source, 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer[:10] == [
        'def f(a):',
        '    """',
        '',
        '    Args:',
        '        a:',
        '',
        '    Returns:',
        '        ',
        '',
        '    """',
        ]


class CountingBuffer(FakeBuffer):
    """FakeBuffer that counts line reads.
    """

    reads = 0

    def __getitem__(self, index: int | slice) -> str | list[str]:
        """Count the read, then index as a list does.
        """
        CountingBuffer.reads += 1
        return super().__getitem__(index)


def test_full_docstring_reads_only_past_the_object_end(vim):
    """Verify :Docstring stops reading the buffer soon after the object ends.

    Mutation: reading every line below the cursor before the scan, which
    makes the command's cost grow with the rest of the buffer.
    Oracle: f ends at line 3, so a few dozen reads cover it; the buffer
    holds 10,000 lines after it.
    """
    source = 'def f(a):\n    return a\n\n' + 'x = 1\n' * 10_000
    vim.load(source, 1, {'python_style': 'google'})
    vim.current.buffer = CountingBuffer(vim.current.buffer)
    CountingBuffer.reads = 0
    Docstring().full_docstring()
    assert vim.current.buffer[1] == '    """'
    assert CountingBuffer.reads < 50


def test_method_first_argument_reads_up_only_to_the_start_line(vim):
    """Verify the upward scan stops reading at the nearest column-0 class.

    Mutation: reading and tokenizing every line above the cursor, which
    makes the command's cost grow with the buffer above the def.
    Oracle: class A is the line above h, so a few dozen reads cover it; the
    buffer holds 10,000 lines above class A.
    """
    source = 'x = 1\n' * 10_000 + 'class A:\n    def h(this, b):\n        pass\n'
    vim.load(source, 10_002, {'python_style': 'rest'})
    vim.current.buffer = CountingBuffer(vim.current.buffer)
    CountingBuffer.reads = 0
    Docstring().full_docstring()
    reads = CountingBuffer.reads
    listed = [
        line.split()[1].rstrip(':') for line in vim.current.buffer if ':param' in line
        ]
    assert listed == ['b']
    assert reads < 50


def test_full_docstring_stops_at_a_string_below_the_object(vim):
    """Verify a column-0 triple quote below the def does not join the def.

    Mutation: reading any line that opens with a triple quote as body, so
    the unclosed string below f joins it and the command raises
    InvalidSyntax.
    Oracle: ast.parse of the buffer above the string ends f at 'return a';
    hand-written Google docstring for f.
    """
    source = 'def f(a):\n    return a\n"""unclosed\n'
    vim.load(source, 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer == [
        'def f(a):',
        '    """',
        '',
        '    Args:',
        '        a:',
        '',
        '    Returns:',
        '        ',
        '',
        '    """',
        '    return a',
        '"""unclosed',
        '',
        ]


@pytest.mark.parametrize(
    ('source', 'row', 'expected'),
    [
        (
            ('class A:\n    def g(self):\n        s = """\nx\n"""\n'
             '        return s\n\n    def h(this, b):\n        pass\n'),
            8,
            ['b'],
            ),
        (
            'class A:\n    s = """\nx\n"""\n\n    def h(this, b):\n        pass\n',
            6,
            ['b'],
            ),
        (
            'class A:\n    @deco("""\nx\n""")\n    def h(this, b):\n        pass\n',
            5,
            ['b'],
            ),
        (
            ('def outer():\n    s = """\nclass Fake:\n    """\n\n'
             '    def h(this, b):\n        pass\n'),
            6,
            ['this', 'b'],
            ),
        (
            ('class A:\n    s = """\ndef fake():\n"""\n    t = \'"""x\'\n'
             '    def h(this, b):\n        pass\n'),
            6,
            ['b'],
            ),
        (
            ("class A:\n    x = 'abc\\\ndef f(): y = ' + \\\n    + w\n"
             '    if True:\n        def h(this, b):\n            pass\n'),
            6,
            ['b'],
            ),
        ])
def test_method_first_argument_ignores_lines_inside_a_string(
    vim, source, row, expected):
    """Verify string lines left of the def's indent do not decide binding.

    Mutation: reading indentation only in the upward scan, so a closing
    triple quote at column 0 ends it as a non-class (lists this) and
    'class Fake:' inside a string ends it as a class (drops this); or, on
    Python 3.11 only, reading past an ERRORTOKEN that opens a string, so
    tokens from 'def fake():' pass and a closing quote ends the scan (the
    last two list this).
    Oracle: README Features, a method's first argument is left out unless
    the method is a @staticmethod; h's enclosing block is class A in all
    but the fourth, where it is def outer.
    """
    vim.load(source, row, {'python_style': 'rest'})
    Docstring().full_docstring()
    listed = [
        line.split()[1].rstrip(':') for line in vim.current.buffer if ':param' in line
        ]
    assert listed == expected


@pytest.mark.parametrize(
    ('source', 'row', 'expected'),
    [
        (
            ('x = """unterminated\n\nclass A:\n    def g(self):\n'
             '        """Doc."""\n        return 1\n\n    def h(this, b):\n'
             '        pass\n'),
            8,
            ['b'],
            ),
        (
            ('class A:\n    s = """unterminated\n    @staticmethod\n'
             '    @deco("""x""")\n    def h(a, b):\n        pass\n'),
            5,
            ['a', 'b'],
            ),
        (
            ('class A:\n    s = """unterminated\n    def g(self):\n'
             '        x = (1 if y\n  else 2)\n        def h(this, b):\n'
             '            pass\n'),
            6,
            ['this', 'b'],
            ),
        ])
def test_method_first_argument_ignores_marks_when_tokenize_fails(
    vim, source, row, expected):
    """Verify an unterminated string above the def leaves binding to indents.

    Mutation: trusting the continuation marks gathered before tokenize
    raises, so wrongly paired quotes hide class A (lists this) or
    @staticmethod (drops a); or skipping compound headers on that path,
    so 'else 2)' passes for one and class A decides (drops this).
    Oracle: HEAD's indentation-only output; README Features, a method's
    first argument is left out unless the method is a @staticmethod.
    """
    vim.load(source, row, {'python_style': 'rest'})
    Docstring().full_docstring()
    listed = [
        line.split()[1].rstrip(':') for line in vim.current.buffer if ':param' in line
        ]
    assert listed == expected


def test_method_first_argument_ignores_lines_inside_an_fstring_field(vim):
    """Verify lines of a multi-line f-string replacement field are skipped.

    Mutation: marking only STRING tokens, so on Python 3.12+ the field's
    column-0 lines end the upward scan as a non-class (lists this).
    Oracle: README Features, a method's first argument is left out unless
    the method is a @staticmethod; tokenize docs, an f-string runs from
    FSTRING_START to its FSTRING_END on 3.12+ and is one STRING on 3.11.
    """
    source = (
        'class A:\n    def g(self):\n        s = f"""\n{\nself\n}\n"""\n'
        '        return s\n\n    def h(this, b):\n        pass\n')
    vim.load(source, 10, {'python_style': 'rest'})
    Docstring().full_docstring()
    listed = [
        line.split()[1].rstrip(':') for line in vim.current.buffer if ':param' in line
        ]
    assert listed == ['b']


def test_full_docstring_reads_past_an_fstring_field(vim):
    """Verify a multi-line f-string replacement field does not end the def.

    Mutation: dropping the open-statement check in
    BufferReader.continues_line, so a line counts only once its statement's
    NEWLINE is read, and on Python 3.12+ the field's column-0 line ends the
    object early and the command raises InvalidSyntax.
    Oracle: hand-written Google docstring for f; tokenize docs, an
    f-string runs from FSTRING_START to its FSTRING_END on 3.12+.
    """
    source = 'def f(a):\n    s = f"""\n{\na\n}\n"""\n    return s\n'
    vim.load(source, 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer[:10] == [
        'def f(a):',
        '    """',
        '',
        '    Args:',
        '        a:',
        '',
        '    Returns:',
        '        ',
        '',
        '    """',
        ]


@pytest.mark.parametrize(
    ('source', 'row', 'body_indent'),
    [
        ('def f(a):\n    x = [\n1]\n    return x\n', 1, '    '),
        ('def f(a):\n    x = 1 + \\\n(2 +\n3)\n    return x\n', 1, '    '),
        ('def f(a):\n    if (a and\na):\n        return a\n', 1, '    '),
        (
            'def f(a):\n    @deco(\n1)\n    def h():\n        pass\n    return h\n',
            1,
            '    ',
            ),
        (
            ('class A:\n    def g(self, a):\n        x = (1 if a\nelse 2)\n'
             '        return x\n'),
            2,
            '        ',
            ),
        ])
def test_full_docstring_reads_past_continuation_lines(vim, source, row, body_indent):
    """Verify a column-0 line that continues a statement does not end the def.

    Mutation: checking only indent, strings and a trailing backslash in the
    downward scan, so '1]', '3)', 'a):', '1)' or 'else 2)' ends the object
    early and the command raises InvalidSyntax.
    Oracle: ast.parse of the whole buffer ends the def on its last line;
    README Features, a body that holds a return gets a returns section.
    """
    vim.load(source, row, {'python_style': 'google'})
    Docstring().full_docstring()
    lines = source.split('\n')
    assert vim.current.buffer == [
        *lines[:row],
        f'{body_indent}"""',
        '',
        f'{body_indent}Args:',
        f'{body_indent}    a:',
        '',
        f'{body_indent}Returns:',
        f'{body_indent}    ',
        '',
        f'{body_indent}"""',
        *lines[row:],
        ]


def test_full_docstring_stops_below_a_comment_ending_in_backslash(vim):
    """Verify a backslash inside a comment does not pull the next line in.

    Mutation: treating any line after one that ends in a backslash as body,
    so the column-0 raise lands in f's Raises section.
    Oracle: ast.parse of the buffer, where a comment's backslash continues
    nothing and the raise is a module-level statement.
    """
    source = 'def f(a):\n    return a  # note \\\nraise ValueError\n'
    vim.load(source, 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer == [
        'def f(a):',
        '    """',
        '',
        '    Args:',
        '        a:',
        '',
        '    Returns:',
        '        ',
        '',
        '    """',
        '    return a  # note \\',
        'raise ValueError',
        '',
        ]


@pytest.mark.parametrize(
    ('source', 'row', 'expected'),
    [
        ('class A:\n    if X:\n        def h(this, b):\n            pass\n', 3, ['b']),
        (
            ('class A:\n    try:\n        pass\n    except E:\n'
             '        def h(this, b):\n            pass\n'),
            5,
            ['b'],
            ),
        (
            ('class A:\n    def g(self):\n        if X:\n'
             '            def h(this, b):\n                pass\n'),
            4,
            ['this', 'b'],
            ),
        ])
def test_method_first_argument_looks_past_compound_statements(
    vim, source, row, expected):
    """Verify an if or except header between the def and its scope is skipped.

    Mutation: ending the upward scan at the first lower-indent line (lists
    this under if X or except E), or skipping a def header as well (drops
    this under def g).
    Oracle: README Features, a method's first argument is left out unless
    the method is a @staticmethod; Python makes a def in an if or except
    block of a class body a method, and one inside a def a function.
    """
    vim.load(source, row, {'python_style': 'rest'})
    Docstring().full_docstring()
    listed = [
        line.split()[1].rstrip(':') for line in vim.current.buffer if ':param' in line
        ]
    assert listed == expected


@pytest.mark.parametrize(
    ('source', 'row', 'expected'),
    [
        ('class A:\n    x = [\n1]\n\n    def h(this, b):\n        pass\n', 5, ['b']),
        (
            'class A:\n    if (X and\nY):\n        def h(this, b):\n            pass\n',
            4,
            ['b'],
            ),
        (
            'class A:\n    x = 1 + \\\n2\n\n    def h(this, b):\n        pass\n',
            5,
            ['b'],
            ),
        ('class A:\n    @deco(\n1)\n    def h(this, b):\n        pass\n', 4, ['b']),
        ('class A(\nBase):\n    def h(this, b):\n        pass\n', 3, ['b']),
        (
            'class A:\n    x = (1 if y\nelse 2)\n\n    def h(this, b):\n        pass\n',
            5,
            ['b'],
            ),
        ])
def test_method_first_argument_ignores_continuation_lines(
    vim, source, row, expected):
    """Verify a line that continues a statement above does not decide binding.

    Mutation: reading each line on its own in the upward scan, so a
    bracket, backslash or decorator continuation at column 0 ends it as a
    non-class (lists this), or 'else 2)' passes for a compound header.
    Oracle: README Features, a method's first argument is left out unless
    the method is a @staticmethod; the ast parent of h is class A in each.
    """
    vim.load(source, row, {'python_style': 'rest'})
    Docstring().full_docstring()
    listed = [
        line.split()[1].rstrip(':') for line in vim.current.buffer if ':param' in line
        ]
    assert listed == expected
