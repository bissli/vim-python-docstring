"""Real Vim loads the plugin through autoload/vimpythondocstring.vim.
"""
import shutil
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent.parent
PLUGIN_DIRS = ['autoload', 'plugin', 'python', 'styles']


def run_vim(plugin_dir: Path, target: Path, *commands: str) -> None:
    """Run headless Vim with only this plugin on the runtimepath.

    Parameters
    ----------
    plugin_dir : Path
        Plugin root added to the front of the runtimepath.
    target : Path
        File Vim opens with the cursor on line 1; Vim writes it back on exit.
    *commands : str
        Ex commands run after the plugin loads, before the write.
    """
    assert shutil.which('vim'), 'tests/integration needs vim with +python3 on PATH'
    ex_args = []
    for command in ['runtime plugin/vim-python-docstring.vim', '1', *commands, 'wq']:
        ex_args += ['-c', command]
    subprocess.run(
        ['vim', '-u', 'NONE', '-N', '-es', '--cmd', f'set rtp^={plugin_dir}',
         *ex_args, str(target)],
        check=False,
        timeout=30)


def test_docstring_command_loads_deps_from_venv(tmp_path):
    """Verify :Docstring in real Vim writes a NumPy docstring using .venv/deps.

    Mutation: autoload adds the wrong dependency directory to sys.path,
    or install.sh installs somewhere autoload does not look.
    Oracle: hand-written NumPy docstring for a one-argument function.
    """
    target = tmp_path / 'target.py'
    target.write_text('def foo(a):\n    return a\n')
    run_vim(REPO_DIR, target, "let g:python_style = 'numpy'", 'Docstring')
    assert target.read_text() == (
        'def foo(a):\n'
        '    """\n'
        '\n'
        '    Parameters\n'
        '    ----------\n'
        '    a :\n'
        '\n'
        '    Returns\n'
        '    -------\n'
        '\n'
        '    """\n'
        '    return a\n')


def test_missing_deps_error_names_install_script(tmp_path):
    """Verify a plugin copy with no .venv reports the missing module and install.sh.

    Mutation: the autoload import loses its ModuleNotFoundError rewrite,
    so the user sees only "No module named 'ibis'".
    Oracle: the message text autoload/vimpythondocstring.vim raises.
    """
    plugin_dir = tmp_path / 'plugin-copy'
    for name in PLUGIN_DIRS:
        shutil.copytree(REPO_DIR / name, plugin_dir / name)
    target = tmp_path / 'target.py'
    target.write_text('def foo(a):\n    return a\n')
    error_file = tmp_path / 'error.txt'
    run_vim(
        plugin_dir,
        target,
        f'try | call vimpythondocstring#Full() | catch | call writefile([v:exception], "{error_file}") | endtry')
    expected_error = 'vim-python-docstring: ibis is missing, run install.sh in the plugin directory'
    assert expected_error in error_file.read_text()
    assert target.read_text() == 'def foo(a):\n    return a\n'
