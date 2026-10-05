"""Stub of Vim's embedded `vim` module, installed before any plugin import.
"""
import sys
import types
from pathlib import Path

import pytest

AUTOLOAD_DIR = str(Path(__file__).resolve().parent.parent / 'autoload')


class FakeBuffer(list):
    """Vim buffer as a list of lines.
    """

    def append(self, text: str, nr: int) -> None:
        """Put text at 0-based index nr, as Vim's `buffer.append` does.
        """
        self.insert(nr, text)


class FakeVim(types.ModuleType):
    """One buffer, a cursor, and the `g:` variables `vim.eval` reads.
    """

    def __init__(self) -> None:
        super().__init__('vim')
        self.current = types.SimpleNamespace(
            buffer=FakeBuffer(),
            window=types.SimpleNamespace(cursor=(1, 0)),
            line='')
        self.globals = {}

    def load(self, source: str, cursor_row: int, globals_: dict | None = None) -> None:
        """Replace the buffer with source and put the cursor on cursor_row.

        Parameters
        ----------
        source : str
            Buffer text, split on newlines.
        cursor_row : int
            1-based row, as Vim's `window.cursor` reports it.
        globals_ : dict, optional
            `g:` variables by bare name, e.g. {'python_style': 'numpy'}.
        """
        self.current.buffer = FakeBuffer(source.split('\n'))
        self.current.window.cursor = (cursor_row, 0)
        self.current.line = self.current.buffer[cursor_row - 1]
        self.globals = dict(globals_ or {})

    def eval(self, expr: str) -> str:
        """Value of one of the expressions the plugin passes to `vim.eval`.

        Raises
        ------
        KeyError
            expr is an expression the stub does not know.
        """
        if expr == 's:plugin_root_dir':
            return AUTOLOAD_DIR
        if expr.startswith('exists("g:'):
            name = expr[len('exists("g:'):-2]
            return '1' if name in self.globals else '0'
        if expr.startswith('g:'):
            return self.globals[expr[2:]]
        raise KeyError(expr)


fake_vim = FakeVim()
sys.modules['vim'] = fake_vim


@pytest.fixture
def vim() -> FakeVim:
    return fake_vim
