let s:plugin_root_dir = fnamemodify(resolve(expand('<sfile>:p')), ':h')

python3 << EOF
import sys
from os.path import normpath, join
import vim
plugin_root_dir = vim.eval('s:plugin_root_dir')
scr = join(plugin_root_dir, '..', 'python')
python_root_dir = normpath(join(plugin_root_dir, '..', 'python'))
# install.sh puts only requirements.txt here. The venv's own
# site-packages stays off sys.path so its pip and setuptools never
# shadow Vim's.
deps = [scr, join(plugin_root_dir, '..', '.venv', 'deps')]
sys.path[0:0] = deps
try:
    import pydocstring
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        f'vim-python-docstring: {exc.name} is missing, run install.sh in the plugin directory') from exc
EOF

" Echo a:exception as an error, without the
" 'Vim(python3):<ExceptionClass>:' prefix Vim puts before it.
function! s:handle_error(exception)
    echohl ErrorMsg
    echo join(map(split(a:exception, ":")[2:], 'trim(v:val)'), " : ")
    echohl None
endfunction

" Write the full docstring for the object on the cursor line, echoing
" any error.
function! vimpythondocstring#Full()
    try
        python3 pydocstring.Docstring().full_docstring()
    catch
        call s:handle_error(v:exception)
    endtry
endfunction

" As vimpythondocstring#Full(), with argument annotations listed.
function! vimpythondocstring#FullTypes()
    try
        python3 pydocstring.Docstring().full_docstring(print_hints=True)
    catch
        call s:handle_error(v:exception)
    endtry
endfunction

" Write an empty one-line docstring below the signature, echoing any
" error.
function! vimpythondocstring#Oneline()
    try
        python3 pydocstring.Docstring().oneline_docstring()
    catch
        call s:handle_error(v:exception)
    endtry
endfunction
