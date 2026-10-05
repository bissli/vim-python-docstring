import abc

import vim


class Enviroment(abc.ABC):
    """Editor state a docstring command reads, and the buffer it writes.
    """

    @property
    @abc.abstractmethod
    def plugin_root_dir(self) -> str:
        """Absolute path of the plugin's autoload directory.

        Returns
        -------
        str
            It sits beside the python and styles directories.
        """

    @property
    @abc.abstractmethod
    def python_style(self) -> str:
        """Docstring style name, e.g. google or numpy.

        Returns
        -------
        str
            A name that has <name>-method.txt and <name>-class.txt templates
            in the styles directory.
        """

    @property
    @abc.abstractmethod
    def python_indent(self) -> str:
        """One indent level of the Python source, e.g. 4 spaces or a tab.
        """

    @property
    @abc.abstractmethod
    def current_line_nr(self) -> int:
        """0-based row of the cursor.
        """

    @property
    @abc.abstractmethod
    def current_line(self) -> str:
        """Text of the cursor's line.
        """

    @abc.abstractmethod
    def append_after_line(self, line_nr: int, text: str) -> None:
        """Insert text into the buffer below line_nr.

        Parameters
        ----------
        line_nr : int
            0-based row the text goes below.
        text : str
            Newline-joined lines, one buffer line each.
        """

    @abc.abstractmethod
    def lines_preceding_cursor(self):
        """Lines above the cursor, nearest first.
        """

    @abc.abstractmethod
    def lines_following_cursor(self):
        """(row, line) pairs from the cursor's line down, row 0-based.
        """


class VimEnviroment(Enviroment):
    """Enviroment over Vim's current buffer and window, and its g: variables.
    """

    def __init__(self) -> None:
        pass

    def _get_var(self, name: str) -> str:
        """Value of the Vim expression name.
        """
        return vim.eval(name)

    @property
    def plugin_root_dir(self) -> str:
        return self._get_var('s:plugin_root_dir')

    @property
    def python_style(self) -> str:
        if not int(vim.eval('exists("g:python_style")')):
            return 'google'
        else:
            return self._get_var('g:python_style')

    @property
    def python_indent(self) -> str:
        if not int(vim.eval('exists("g:vpd_indent")')):
            return '    '
        else:
            return self._get_var('g:vpd_indent')

    @property
    def current_line_nr(self) -> int:
        return vim.current.window.cursor[0] - 1

    @property
    def current_line(self) -> str:
        return vim.current.line

    def append_after_line(self, line_nr: int, text: str) -> None:
        line_nr += 1
        for line in reversed(text.split('\n')):
            vim.current.buffer.append(line, line_nr)

    def lines_preceding_cursor(self):
        buffer = vim.current.buffer
        for row in range(vim.current.window.cursor[0] - 2, -1, -1):
            yield buffer[row]

    def lines_following_cursor(self):
        buffer = vim.current.buffer
        cursor_row = vim.current.window.cursor[0] - 1
        current_row = cursor_row
        while True:
            if current_row > len(vim.current.buffer) - 1:
                return
            yield current_row, buffer[current_row]
            current_row += 1
