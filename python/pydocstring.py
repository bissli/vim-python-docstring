#!/usr/bin/env python3
"""Write a docstring for the def or class on Vim's cursor line.
"""
import abc
import ast
import os
import re
import tokenize
from collections.abc import Iterator

import ibis
from asthelper import ClassInstanceNameExtractor, ClassVisitor, MethodVisitor
from utils import concat_
from vimenv import Enviroment, VimEnviroment

COMPOUND_HEADER = r'(async\s+)?(if|elif|else|try|except|finally|with|for|while|match|case)\b'


class InvalidSyntax(Exception):
    """Raise when the syntax of processed object is invalid.
    """


class DocstringUnavailable(Exception):
    """Raise when trying to process object to which there is no docstring.
    """


class Templater:
    """Renders a style's method or class template into an indented docstring.

    Parameters
    ----------
    location : str
        The plugin's autoload directory. Templates are read from
        location/../styles.
    indent : str
        One indent level, e.g. 4 spaces or a tab.
    style : str, default 'google'
        Template name prefix, e.g. google, numpy, rest or epytext.

    Attributes
    ----------
    template : ibis.Template
        The template the last get_*_docstring call rendered.
    """

    def __init__(self, location: str, indent: str, style: str = 'google') -> None:
        self.style = style
        self.indent = indent
        self.location = location

    def _docstring_helper(self, obj_indent: str, docstring: str) -> str:
        """docstring, each non-empty line prefixed by obj_indent and indent.
        """
        lines = []
        for line in docstring.split('\n'):
            if re.match('.', line):
                line = concat_(obj_indent, self.indent, line)
            lines.append(line)

        return '\n'.join(lines)

    def get_method_docstring(
        self,
        method_indent: str,
        args: list[dict],
        returns: bool,
        yields: bool,
        raises: list[str],
        print_hints: bool = False) -> str:
        """Method docstring rendered from the style's method template.

        Parameters
        ----------
        method_indent : str
            Leading whitespace of the def line.
        args : list[dict]
            {'arg': name, 'type': annotation source or None} per argument,
            as `MethodVisitor.arguments` holds them.
        returns : bool
            True to render the returns section.
        yields : bool
            True to render the yields section.
        raises : list[str]
            Exception names for the raises section, in order.
        print_hints : bool, default False
            True to render each argument's annotation.

        Returns
        -------
        str
            Newline-joined lines, each non-empty one indented one level past
            method_indent.

        Raises
        ------
        FileNotFoundError
            styles/ has no <style>-method.txt.
        """
        with open(
            os.path.join(self.location, '..', f'styles/{self.style}-method.txt')) as f:
            self.template = ibis.Template(f.read())
        docstring = self.template.render(
            indent=self.indent,
            args=args,
            hints=print_hints,
            raises=raises,
            returns=returns,
            yields=yields)
        return self._docstring_helper(method_indent, docstring)

    def get_class_docstring(self, class_indent: str, attr: list[str]) -> str:
        """Class docstring rendered from the style's class template.

        Parameters
        ----------
        class_indent : str
            Leading whitespace of the class line.
        attr : list[str]
            Instance attribute names, in order.

        Returns
        -------
        str
            Newline-joined lines, each non-empty one indented one level past
            class_indent.

        Raises
        ------
        FileNotFoundError
            styles/ has no <style>-class.txt.
        """
        with open(
            os.path.join(self.location, '..', f'styles/{self.style}-class.txt')) as f:
            self.template = ibis.Template(f.read())
        docstring = self.template.render(indent=self.indent, attr=attr)
        return self._docstring_helper(class_indent, docstring)


class BufferReader:
    """Buffer lines in source order, read only as far as a caller asks.

    Parameters
    ----------
    rows : Iterator[tuple[int, str]]
        (row, line) pairs in source order. An offset counts pairs from the
        first one.

    Attributes
    ----------
    tokenize_failed : bool
        True once tokenizing has raised, or on 3.11 yielded an error token
        for an unterminated string, e.g. at a dedent below the object, an
        unterminated string or bytes that are not UTF-8. Tokenizing stops
        there for good. Marks read before the error stay, and an
        unterminated string raises only at the last line.
    """

    def __init__(self, rows: Iterator[tuple[int, str]]) -> None:
        self._rows = rows
        self._read = []
        self._token_offset = 0
        self._tokens = tokenize.generate_tokens(self._next_token_line)
        self._token_row = 0
        self._tokens_done = False
        self.tokenize_failed = False
        self._continued_offsets = set()
        self._logical_row = 0

    def row(self, offset: int) -> tuple[int, str] | None:
        """(row, line) pair at offset, None past the end.
        """
        while len(self._read) <= offset:
            buffer_row = next(self._rows, None)
            if buffer_row is None:
                return None
            self._read.append(buffer_row)
        return self._read[offset]

    def _next_token_line(self) -> str:
        """The tokenizer's readline: the next line it has not seen, or ''.
        """
        buffer_row = self.row(self._token_offset)
        if buffer_row is None:
            return ''
        self._token_offset += 1
        return buffer_row[1] + '\n'

    def tokenize_to(self, offset: int) -> None:
        """Tokenize until a token starts on the line at offset or below it.

        Parameters
        ----------
        offset : int
            As for `row`. Past the last line, tokenizes to the end.
        """
        while not self._tokens_done and self._token_row <= offset:
            try:
                token = next(self._tokens)
            except StopIteration:
                self._tokens_done = True
                break
            except (tokenize.TokenError, SyntaxError, UnicodeError):
                self._tokens_done = True
                self.tokenize_failed = True
                break
            self._token_row = token.start[0]
            token_name = tokenize.tok_name[token.type]
            # Python 3.11 yields an ERRORTOKEN opening with a quote for an
            # unterminated single-quoted string, where 3.12+ raises. Its
            # other ERRORTOKENs mark valid non-ASCII names.
            if token_name == 'ERRORTOKEN' and re.match(r'[A-Za-z]*[\'"]', token.string):
                self._tokens_done = True
                self.tokenize_failed = True
                break
            if token_name == 'NEWLINE':
                self._continued_offsets.update(
                    range(self._logical_row, token.start[0]))
                self._logical_row = 0
            elif (not self._logical_row
                  and token_name not in {'NL', 'COMMENT', 'INDENT', 'DEDENT'}):
                self._logical_row = token.start[0]

    def continues_line(self, offset: int) -> bool:
        """True when the line at offset is not the first line of its statement.

        Parameters
        ----------
        offset : int
            As for `row`.

        Returns
        -------
        bool
            True for a line inside brackets, after a backslash or inside a
            multi-line string or f-string. Tokenizes only as far as
            `tokenize_to(offset)` does. A line past a tokenize error can
            read either way. `tokenize_failed` reports the error.
        """
        self.tokenize_to(offset)
        return offset in self._continued_offsets or 0 < self._logical_row <= offset


class ObjectWithDocstring(abc.ABC):
    """The def or class on the cursor line, and the editor it is in.

    Parameters
    ----------
    env : Enviroment
        Editor state. Its cursor line starts the object.
    templater : Templater
        Renders the full docstring.
    """

    def __init__(self, env: Enviroment, templater: Templater) -> None:
        self.env = env
        self.templater = templater

    @abc.abstractmethod
    def write_docstring(self, *args: bool, **kwargs: bool) -> None:
        """Write the full docstring into `self.env` below the signature.

        Parameters
        ----------
        *args, **kwargs : bool
            Options a subclass reads, e.g. print_hints.
        """

    def _get_sig(self) -> tuple[int, str]:
        """Where the signature on the cursor line ends, and its indent.

        Returns
        -------
        tuple[int, str]
            0-based row of the line that ends the signature, and the leading
            whitespace of the cursor line.

        Raises
        ------
        InvalidSyntax
            The buffer ends before the signature parses.
        DocstringUnavailable
            The object's body is on its signature line.
        """
        lines = []
        lines_it = self.env.lines_following_cursor()
        sig_line, first_line = next(lines_it)
        indent = re.findall(r'^(\s*)', first_line)[0]

        lines.append(first_line)

        while not self._is_valid('\n'.join(lines))[0]:
            try:
                sig_line, line = next(lines_it)
            except StopIteration as e:
                raise InvalidSyntax('Object does not have valid syntax')
            lines.append(line)
        return sig_line, indent

    def _object_tree(self) -> tuple[int, str, ast.Module]:
        """Parse the def or class on the cursor line, read down to its end.

        Returns
        -------
        tuple[int, str, ast.Module]
            0-based row of the line that ends the signature, the leading
            whitespace of the cursor line, and the object's source parsed
            with that whitespace removed.

        Raises
        ------
        InvalidSyntax
            The object's source does not parse.
        DocstringUnavailable
            The object's body is on its signature line.
        """
        reader = BufferReader(self.env.lines_following_cursor())
        sig_line, first_line = reader.row(0)
        lines = [first_line]

        obj_indent = re.findall(r'^(\s*)', first_line)[0]
        expected_indent = concat_(obj_indent, self.env.python_indent)

        valid_sig, _ = self._is_valid(first_line)

        offset = 1
        while (buffer_row := reader.row(offset)) is not None:
            last_row, line = buffer_row
            if (valid_sig
                and not self._is_correct_indent(line, expected_indent)
                and not reader.continues_line(offset)):
                break

            lines.append(line)
            if not valid_sig:
                data = '\n'.join(lines)
                valid_sig, _ = self._is_valid(data)
                sig_line = last_row
            offset += 1

        lines = [re.sub('^' + obj_indent, '', l) for l in lines]
        for i, l in enumerate(reversed(lines)):
            if l.strip() == '':
                lines.pop()
            else:
                break
        if len(lines) == 1:
            lines.append(f'{self.env.python_indent}pass')

        data = '\n'.join(lines)
        try:
            tree = ast.parse(data)
        except Exception as e:
            raise InvalidSyntax('Object has invalid syntax.')

        return sig_line, obj_indent, tree

    def _is_correct_indent(self, line: str, expected_indent: str) -> bool:
        """True when line still belongs to the object's body.

        Parameters
        ----------
        line : str
            The line to test.
        expected_indent : str
            The body's indent.

        Returns
        -------
        bool
            True for a line indented at least expected_indent, a comment or
            a blank line.
        """
        if re.match(r'^' + expected_indent, line):
            return True
        elif re.match(r'^\s*#', line):
            return True
        elif re.match(r'^\s*$', line):
            return True

        return False

    def _is_valid(self, lines: str) -> tuple[bool, ast.Module | None]:
        """Whether lines hold a whole signature, parsed with a pass body.

        Parameters
        ----------
        lines : str
            Newline-joined source from the def or class line down.

        Returns
        -------
        tuple[bool, ast.Module or None]
            True and the tree when lines plus an indented pass parse, else
            False and None.

        Raises
        ------
        DocstringUnavailable
            lines parse alone, so the body is on the signature line.
        """
        try:
            ast.parse(lines.lstrip())
        except SyntaxError:
            pass
        else:
            raise DocstringUnavailable('Object body is on its signature line')
        func = concat_(lines.lstrip(), '\n    pass')
        try:
            tree = ast.parse(func)
            return True, tree
        except SyntaxError as e:
            return False, None

    def write_simple_docstring(self) -> None:
        """Write an empty one-line docstring below the signature.

        Raises
        ------
        InvalidSyntax
            The buffer ends before the signature parses.
        DocstringUnavailable
            The object's body is on its signature line.
        """
        sig_line, indent = self._get_sig()
        docstring = concat_(indent, self.templater.indent, '"""  """')
        self.env.append_after_line(sig_line, docstring)


class MethodController(ObjectWithDocstring):
    """A def on the cursor line, documented from its signature and body.
    """

    def _is_bound_method(self) -> bool:
        """True when the def under the cursor is a method that is not static.

        Returns
        -------
        bool
            True when the nearest class, def or async def line above at a
            lower indent is a class, past any compound statement header
            such as if or try. A line that continues a statement, in
            brackets, after a backslash or inside a string, is skipped. When
            the lines above do not tokenize, indentation alone decides and
            no header is skipped. Can be wrong below a column-0 class or def
            line inside a multi-line string, when the lines from it down
            still tokenize.
        """
        def_indent = len(self.env.current_line) - len(self.env.current_line.lstrip())
        if not def_indent:
            return False
        preceding = self.env.lines_preceding_cursor()
        lines_above = []
        for line in preceding:
            lines_above.append(line)
            if re.match(r'(class|def|async\s+def)\s', line):
                break
        lines_above.reverse()
        reader = BufferReader(enumerate(lines_above))
        # Tokenize to the end first: the marks read before an error can
        # pair the wrong quotes.
        reader.tokenize_to(len(lines_above))
        # A start line inside a string almost always leaves an odd triple
        # quote or an unmatched bracket below it, so the tokenize fails.
        if reader.tokenize_failed and (lines_further_up := list(preceding)):
            lines_above = lines_further_up[::-1] + lines_above
            reader = BufferReader(enumerate(lines_above))
            reader.tokenize_to(len(lines_above))
        in_decorators = True
        block_indent = def_indent
        for offset in reversed(range(len(lines_above))):
            line = lines_above[offset]
            stripped = line.strip()
            if (not stripped
                or stripped.startswith('#')
                or (not reader.tokenize_failed and reader.continues_line(offset))):
                continue
            indent = len(line) - len(line.lstrip())
            if in_decorators and indent > def_indent:
                continue
            if in_decorators and indent == def_indent and stripped.startswith('@'):
                if stripped[1:].lstrip().startswith('staticmethod'):
                    return False
                continue
            in_decorators = False
            if indent < block_indent:
                if not reader.tokenize_failed and re.match(COMPOUND_HEADER, stripped):
                    block_indent = indent
                    continue
                return stripped.startswith('class ')
        return False

    def _process_tree(
        self,
        tree: ast.Module) -> tuple[list[dict], bool, bool, list[str]]:
        """What the docstring of the def in tree lists.

        Parameters
        ----------
        tree : ast.Module
            The def parsed by `_object_tree`.

        Returns
        -------
        tuple[list[dict], bool, bool, list[str]]
            Arguments, whether it returns, whether it yields, and raised
            exception names, as `MethodVisitor` collects them.
        """
        v = MethodVisitor(bound=self._is_bound_method())
        v.visit(tree)
        args = list(v.arguments)
        raises = list(v.raises)
        return args, v.returns, v.yields, raises

    # TODO: set cursor on appropriate position to fill the docstring
    def write_docstring(self, print_hints: bool = False) -> None:
        """Write the def's full docstring below its signature.

        Parameters
        ----------
        print_hints : bool, default False
            True to list each argument's annotation.

        Raises
        ------
        InvalidSyntax
            The def's source does not parse.
        DocstringUnavailable
            The def's body is on its signature line.
        FileNotFoundError
            styles/ has no method template for the style.
        """
        sig_line, method_indent, tree = self._object_tree()
        args, returns, yields, raises = self._process_tree(tree)
        docstring = self.templater.get_method_docstring(
            method_indent,
            args,
            returns,
            yields,
            raises,
            print_hints)
        self.env.append_after_line(sig_line, docstring)


class ClassController(ObjectWithDocstring):
    """A class on the cursor line, documented from its instance attributes.
    """

    def _process_tree(self, tree: ast.Module) -> list[str]:
        """Instance attribute names the class in tree assigns, in source order.

        Parameters
        ----------
        tree : ast.Module
            The class parsed by `_object_tree`.

        Returns
        -------
        list[str]
            Attributes of the instance name `ClassInstanceNameExtractor`
            finds.
        """
        x = ClassInstanceNameExtractor()
        x.visit(tree)
        v = ClassVisitor(x.instance_name)
        v.visit(tree)
        att = list(v.attributes)
        return att

    def write_docstring(self, *args: bool, **kwargs: bool) -> None:
        """Write the class's full docstring below its signature.

        Parameters
        ----------
        *args, **kwargs : bool
            Ignored, so print_hints has no effect on a class.

        Raises
        ------
        InvalidSyntax
            The class's source does not parse.
        DocstringUnavailable
            The class's body is on its signature line.
        FileNotFoundError
            styles/ has no class template for the style.
        """
        sig_line, class_indent, tree = self._object_tree()
        attr = self._process_tree(tree)
        docstring = self.templater.get_class_docstring(class_indent, attr)
        self.env.append_after_line(sig_line, docstring)


class Docstring:
    """The docstring commands for the def or class on Vim's cursor line.

    Attributes
    ----------
    obj_controller : ObjectWithDocstring
        The controller `_controller_factory` picks for the cursor line.

    Raises
    ------
    DocstringUnavailable
        The cursor line starts no def, async def or class.
    """

    def __init__(self) -> None:
        env = VimEnviroment()
        style = env.python_style
        indent = env.python_indent
        location = env.plugin_root_dir
        templater = Templater(location, indent=indent, style=style)

        self.obj_controller = self._controller_factory(env, templater)

    def _controller_factory(
        self,
        env: Enviroment,
        templater: Templater) -> ObjectWithDocstring:
        """Controller for the object that env's cursor line starts.

        Parameters
        ----------
        env : Enviroment
            Its current line picks the controller.
        templater : Templater
            Passed to the controller.

        Returns
        -------
        ObjectWithDocstring
            MethodController for a def or async def line, ClassController
            for a class line.

        Raises
        ------
        DocstringUnavailable
            The line starts no def, async def or class.
        """
        line = env.current_line
        try:
            first_word = re.match(r'^\s*(\w+).*', line).groups()[0]
        except Exception:
            first_word = None
        if first_word == 'def':
            return MethodController(env, templater)
        elif first_word == 'class':
            return ClassController(env, templater)
        elif first_word == 'async':
            second_word_catch = re.match(r'^\s*\w+\s+(\w+).*', line)
            if second_word_catch:
                second_word = second_word_catch.groups()[0]
                if second_word == 'def':
                    return MethodController(env, templater)

        raise DocstringUnavailable('Docstring ERROR: Docstring cannot be created for selected object')

    def full_docstring(self, print_hints: bool = False) -> None:
        """Write the object's full docstring below its signature.

        Parameters
        ----------
        print_hints : bool, default False
            True to list argument annotations, as :DocstringTypes does.

        Raises
        ------
        DocstringUnavailable
            Any failure, its message prefixed with 'Docstring ERROR: '.
        """
        try:
            self.obj_controller.write_docstring(print_hints=print_hints)
        except Exception as e:
            raise DocstringUnavailable(concat_('Docstring ERROR: ', e))

    def oneline_docstring(self) -> None:
        """Write an empty one-line docstring below the object's signature.

        Raises
        ------
        DocstringUnavailable
            Any failure, its message prefixed with 'Docstring ERROR: '.
        """
        try:
            self.obj_controller.write_simple_docstring()
        except Exception as e:
            raise DocstringUnavailable(concat_('Docstring ERROR: ', e))
