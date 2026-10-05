"""Baseline: plugin output pinned to the saved files under expected/.

Each case runs one plugin command on a stub Vim buffer and compares the
whole resulting buffer, or the raised message, with its saved file.
Regenerate a saved file only when the user accepts the new output as the
baseline.
"""
from pathlib import Path
from types import ModuleType

import pytest
from pydocstring import Docstring

EXPECTED_DIR = Path(__file__).parent / 'expected'
STYLES = ['google', 'numpy', 'rest', 'epytext']

METHOD = """\
def foo(self, a, b: int = 1, *, c: "dict[str, int]" = None):
    def inner():
        return 1
    if a:
        raise ValueError("bad")
    return a
"""

GENERATOR = """\
def gen(n,
        m='foo(c,d)'):
    yield n
"""

ASYNC_NO_ARGS = """\
async def run():
    pass
"""

NESTED_METHOD = """\
class Outer:
    def method(self, x):
        # comment at the body's indent

        return x
    other = 1
"""

CLASS = """\
class Thing:
    def __init__(this, x):
        this.a = x
        this.b: int = 2
        this.c.d = 3

    def other(self):
        self.e = 4
"""

TAB_METHOD = """\
def tabbed(a):
\tif a:
\t\traise KeyError(a)
\treturn a
"""

NOT_AN_OBJECT = """\
x = 1
"""

# Each case: id, source, 1-based cursor row, command, g: variables.
CASES = [
    ('method', METHOD, 1, 'full', {}),
    ('method-hints', METHOD, 1, 'full_hints', {}),
    ('generator', GENERATOR, 1, 'full_hints', {}),
    ('async', ASYNC_NO_ARGS, 1, 'full', {}),
    ('nested', NESTED_METHOD, 2, 'full', {}),
    ('class', CLASS, 1, 'full', {}),
    ('oneline', METHOD, 1, 'oneline', {}),
    ('tab-indent', TAB_METHOD, 1, 'full', {'vpd_indent': '\t'}),
    ('indent-mismatch', NESTED_METHOD, 2, 'full', {'vpd_indent': '\t'}),
    ]
STYLED_CASES = [
    pytest.param(
        source, row, command, {**globals_, 'python_style': style},
        f'{case_id}-{style}.txt', id=f'{case_id}-{style}')
    for case_id, source, row, command, globals_ in CASES
    for style in STYLES
    ]
UNSTYLED_CASES = [
    pytest.param(
        METHOD, 1, 'full_hints', {}, 'default-style.txt', id='default-style'),
    pytest.param(
        NOT_AN_OBJECT, 1, 'full', {}, 'not-an-object.txt', id='not-an-object'),
    pytest.param(
        METHOD, 2, 'full', {}, 'cursor-on-inner-def.txt', id='cursor-on-inner-def'),
    ]


def run_command(
    vim: ModuleType,
    source: str,
    row: int,
    command: str,
    globals_: dict) -> str:
    """Run one plugin command on a stub buffer and capture what it left.

    Parameters
    ----------
    vim : ModuleType
        The conftest `FakeVim` stub.
    source : str
        Buffer text.
    row : int
        1-based cursor row.
    command : str
        'full', 'full_hints' (`:DocstringTypes`) or 'oneline'.
    globals_ : dict
        `g:` variables by bare name.

    Returns
    -------
    str
        The buffer joined on newlines, or '<ExceptionType>: <message>' and a
        newline when the command raises.
    """
    vim.load(source, row, globals_)
    try:
        docstring = Docstring()
        if command == 'oneline':
            docstring.oneline_docstring()
        else:
            docstring.full_docstring(print_hints=command == 'full_hints')
    except Exception as exc:
        return f'{type(exc).__name__}: {exc}\n'
    return '\n'.join(vim.current.buffer)


@pytest.mark.parametrize(
    ('source', 'row', 'command', 'globals_', 'expected_name'),
    STYLED_CASES + UNSTYLED_CASES)
def test_output_matches_baseline(
    vim, source, row, command, globals_, expected_name):
    """Verify each command's buffer or error equals the saved baseline output.

    Mutation: any change to the templates, the AST visitors, indentation,
    insertion row, or the error messages the plugin raises.
    Oracle: the saved output under expected/.
    """
    expected = (EXPECTED_DIR / expected_name).read_text()
    assert run_command(vim, source, row, command, globals_) == expected
