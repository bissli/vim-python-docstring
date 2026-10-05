# vim-python-docstring
This is a plugin to Vim and NeoVim for the creation of Python docstrings.

## What it does
Docstrings for methods will contain a **list of parameters and their type hints**, **list of raised exceptions** and whether the method **yields** or **raises**.

Class docstring will have a **list of atributes**.

It uses Python's [ast](https://docs.python.org/3/library/ast.html) library for parsing code.
This makes it quite **robust** solution, which can handle function signature such as

~~~{.python}
def foo(a='foo(c,d)',
    b,
    z):
        pass
~~~


## Installation
The plugin needs Vim built with Python 3.11 or newer, or Neovim whose Python provider runs 3.11 or newer. Neovim's provider is `pynvim`: `pip3 install pynvim`.

`install.sh` creates a plugin-local `.venv` and installs the dependencies pinned in `requirements.txt` into `.venv/deps`, the one directory the plugin adds to Vim's Python path. The script runs on Linux and macOS. A plugin manager runs it after each install or update:

~~~{viml}
" vim-plug
Plug 'bissli/vim-python-docstring', { 'do': './install.sh' }
~~~

~~~{lua}
-- lazy.nvim
{ 'bissli/vim-python-docstring', build = './install.sh' }
~~~

With a manager that has no build hook, or with a manual clone into `~/.vim/pack/<name>/start/`, the user runs `./install.sh` once in the plugin directory.

## Usage
The plugin has only commands which you can map however you like (i use `<leader>ss` for `:Docstring`).

1. Place cursor at the first line of the object (`def ...` of `class ...`) for which you want to create a docstring
2. Then type `:Docstring` or different command

The plugin uses these commands:

| Command | Description |
| ------- | ----------- |
| Docstring     | Create full docstring
| DocstringTypes| Just like `:Docstring` but includes type hints
| DocstringLine | Create empty one-line docstring

## Options:
There are things you can set.

### The `g:vpd_indent` option
String which you use to indent your code.

Default: `'    '` (4 spaces).

~~~{viml}
let g:vpd_indent = '    '
~~~

### The `g:python_style` option
Which docstring style you wish to use.

Default: `'google'`

Possible values = [`'google'`, `'numpy'`, `'rest'`, `'epytext'`]

~~~{viml}
let g:python_style = 'google'
~~~

## Development
Pull requests are welcome as are feature request and issue reports.

The tests need `.venv/bin/pip install pytest`, then run with `.venv/bin/pytest`. `tests/integration` drives a real `vim` on `PATH`. The rest run against a stub `vim` module.

You can encounter some situations in which the plugin may not work as expected.
Most notably there *may* be issues if your keyword for refering to instance is not `self` -- in such case it *may* be added to the list of arguments.
