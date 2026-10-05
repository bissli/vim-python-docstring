# vim-python-docstring
A Vim and Neovim plugin that writes Python docstrings.

## Features
A method docstring lists the method's arguments and the exceptions it
raises. It holds a returns or yields section when the method body holds a
`return` or `yield` statement, a bare `return` included. `:DocstringTypes` adds each argument's type hint.
A method's first argument, its instance or class, is left out of the list
unless the method is a `@staticmethod`. A first argument named `self` or
`cls` is left out in every function.

A class docstring lists the class's attributes.

The plugin parses code with Python's
[ast](https://docs.python.org/3/library/ast.html) module, so it handles a
signature that spans lines or holds parentheses and commas inside a
default value:

~~~{.python}
def foo(a,
        b='foo(c,d)',
        z=None):
    pass
~~~

## Installation
The plugin needs Vim built with Python 3.11 or newer, or Neovim whose
Python provider runs 3.11 or newer. Neovim's provider is `pynvim`:
`pip3 install pynvim`.

`install.sh` creates a plugin-local `.venv` and installs the dependencies
pinned in `requirements.txt` into `.venv/deps`, the one directory the
plugin adds to Vim's Python path. The script runs on Linux and macOS. A
plugin manager runs it after each install or update:

~~~{viml}
" vim-plug
Plug 'bissli/vim-python-docstring', { 'do': './install.sh' }
~~~

~~~{lua}
-- lazy.nvim
{ 'bissli/vim-python-docstring', build = './install.sh' }
~~~

With a manager that has no build hook, or with a manual clone into
`~/.vim/pack/<name>/start/`, the user runs `./install.sh` once in the
plugin directory.

## Usage
The plugin defines commands and no key mappings. Each command writes the
docstring for the object whose first line (`def ...` or `class ...`)
holds the cursor.

| Command           | Docstring                                     |
| ----------------- | --------------------------------------------- |
| `:Docstring`      | Full docstring                                |
| `:DocstringTypes` | Full docstring with each argument's type hint |
| `:DocstringLine`  | Empty one-line docstring                      |

A mapping such as `nnoremap <leader>ss :Docstring<CR>` binds a command to
a key.

## Options

### `g:vpd_indent`
The string that indents one level of code.

Default: `'    '` (4 spaces).

~~~{viml}
let g:vpd_indent = '    '
~~~

### `g:python_style`
The docstring style.

Default: `'google'`

Values: `'google'`, `'numpy'`, `'rest'`, `'epytext'`

~~~{viml}
let g:python_style = 'google'
~~~

## Development
Pull requests, feature requests and issue reports are welcome.

The tests need `.venv/bin/pip install pytest`, and `.venv/bin/pytest`
runs them. `tests/integration` drives a real `vim` on `PATH`. The rest run
against a stub `vim` module.

## Limitations
The Raises list takes a raised name as an exception class only when its
last part, past any leading underscores, starts upper case and is not all
upper case, as `ValueError`, `errors.Timeout` and `E` do. `raise exc`,
`raise self.error` and a lower-case class such as `raise error(...)` add
nothing.

A raise that a handler of its own `try` catches is left out, unless the
handler re-raises it. Two builtin classes match by subclass, so
`except LookupError` catches `KeyError`. A class outside the builtins
counts as an `Exception` subclass, so `except Exception` catches it, but
otherwise matches only by its exact name: `except AppError` leaves
`raise AppTimeout()` in the list even when `AppTimeout` subclasses
`AppError`.
