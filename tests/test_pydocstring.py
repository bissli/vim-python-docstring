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
        'def f(a,', '      b):', '    """  """', '    return a', '',
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
        'def f(a, \\', '      b):', '    """', '', '    Args:', '        a:',
        '        b:', '', '    Returns:', '        ', '', '    """',
        '    return a', '',
        ]


def test_oneline_goes_below_backslash_continued_signature(vim):
    """Verify :DocstringLine inserts after a signature continued with a backslash.

    Mutation: joining signature lines with '' in _get_sig, so the backslash
    no longer ends a line and the scan runs to the buffer's end.
    Oracle: hand-written buffer with the docstring below 'b):'.
    """
    vim.load('def f(a, \\\n      b):\n    return a\n', 1)
    Docstring().oneline_docstring()
    assert vim.current.buffer == [
        'def f(a, \\', '      b):', '    """  """', '    return a', '',
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
        'TypeError', 'KeyError', 'OSError', 'IndexError', 'EOFError',
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
        'def foo():', '  """', '', '  Returns:', '    ', '', '  """',
        '  x = """', 'Comment', '"""', '  return x', '',
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
        'def f(a):', '    """', '', '    Args:', '        a:', '', '    Returns:',
        '        ', '', '    """',
        ]
    assert vim.current.buffer[10:] == source.split('\n')[1:]


@pytest.mark.parametrize(('source', 'row', 'expected'), [
    ('class Shape:\n    def area(this, x):\n        return x\n', 2, ['x']),
    ('class Maker:\n    @staticmethod\n    def make(a):\n        return a\n', 3, ['a']),
    ('class Maker:\n    @classmethod\n    def make(klass, a):\n        return a\n',
     3, ['a']),
    (('class Shape:\n    def area(self):\n        def helper(item):\n'
     '            return item\n        return helper\n'), 3, ['item']),
    ('def f(this, a):\n    return a\n', 1, ['this', 'a']),
    (('class A:\n    @staticmethod\n    def g(a):\n        pass\n\n'
     '    def h(this, b):\n        pass\n'), 6, ['b']),
    (('class A:\n    @staticmethod\n    @deco(\n        1)\n'
      '    def f(a):\n        pass\n'), 5, ['a']),
    ('class A:\n    @ staticmethod\n    def f(a):\n        pass\n', 3, ['a']),
    ])
def test_method_first_argument_is_dropped_by_context(vim, source, row, expected):
    """Verify a method's first argument is dropped whatever its name, and only there.

    Mutation: the old name-only rule (lists this), ignoring @staticmethod
    (drops a), treating an enclosing def as a class (drops item), letting
    an earlier sibling's decorator count (keeps this for h), or ending the
    decorator scan at a continuation line or on '@ staticmethod' (drops a).
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
    """Verify a surrogate-escaped byte in a later function does not block f.

    Mutation: letting tokenize's UnicodeEncodeError out of
    BufferReader.inside_string, which fails the whole command.
    Oracle: hand-written Google docstring for f alone.
    """
    source = 'def f(a):\n    return a\n\n\ndef g(b):\n    s = "caf\udce9"\n'
    vim.load(source, 1, {'python_style': 'google'})
    Docstring().full_docstring()
    assert vim.current.buffer[:10] == [
        'def f(a):', '    """', '', '    Args:', '        a:', '', '    Returns:',
        '        ', '', '    """',
        ]


class CountingBuffer(FakeBuffer):
    """FakeBuffer that counts line reads.
    """

    reads = 0

    def __getitem__(self, index):
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
