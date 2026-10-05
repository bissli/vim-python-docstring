"""MethodVisitor's list of raised exceptions.
"""
import ast

import pytest
from asthelper import MethodVisitor


def raises_of(source: str) -> list[str]:
    """Exception names MethodVisitor collects from source, in its order.
    """
    visitor = MethodVisitor()
    visitor.visit(ast.parse(source))
    return list(visitor.raises)


def test_raises_records_dotted_and_bare_names():
    """Verify a dotted call and a bare class name both appear as written.

    Mutation: reading node.func.id only, which crashes on errors.Foo(),
    or collecting Call nodes only, which drops a bare ValueError.
    Oracle: the names as written in the hand-written source.
    """
    source = (
        'def f(a):\n'
        '    if a:\n'
        '        raise errors.Foo()\n'
        '    raise ValueError\n')
    assert raises_of(source) == ['errors.Foo', 'ValueError']


def test_raises_keep_source_order():
    """Verify Raises lists names by first appearance, stable across runs.

    Mutation: storing raises in a set (order follows the hash seed) or
    sorting them.
    Oracle: the hand-written source order, which is not alphabetical.
    """
    source = (
        'def f(a):\n'
        '    raise TypeError(a)\n'
        '    raise KeyError(a)\n'
        '    def inner():\n'
        '        raise ValueError(a)\n'
        '    raise OSError(a)\n'
        '    raise TypeError(a)\n'
        '    raise IndexError(a)\n')
    assert raises_of(source) == [
        'TypeError',
        'KeyError',
        'ValueError',
        'OSError',
        'IndexError',
        ]


def test_variables_and_unnamed_raises_are_skipped():
    """Verify lower-case names, call results, subscripts and causes add none.

    Mutation: listing every bare or dotted name (adds exc, self.error),
    unparsing any callee (adds err.with_traceback, make_error()), or
    visiting the `from` clause (adds KeyError).
    Oracle: ValueError is the one class the source names as raised.
    """
    source = (
        'def f(self, exc, err, errs, tb):\n'
        '    raise exc\n'
        '    raise self.error\n'
        '    raise err.with_traceback(tb)\n'
        '    raise make_error()(1)\n'
        '    raise errs[0]\n'
        '    raise ValueError("x") from KeyError()\n')
    assert raises_of(source) == ['ValueError']


def test_with_traceback_and_branches_give_the_class():
    """Verify with_traceback, `or` and conditional raises list each class.

    Mutation: dropping the with_traceback unwrap (drops ValueError) or
    skipping BoolOp and IfExp (drops TypeError, KeyError, IndexError).
    Oracle: the classes written in each hand-written raise.
    """
    source = (
        'def f(a, tb, too_long):\n'
        '    raise ValueError("bad").with_traceback(tb)\n'
        '    raise too_long or TypeError(a)\n'
        '    raise KeyError() if a else IndexError()\n')
    assert raises_of(source) == ['ValueError', 'TypeError', 'KeyError', 'IndexError']


@pytest.mark.parametrize(
    ('handler', 'raised', 'expected'),
    [
        ('except KeyError:', 'raise KeyError("k")', []),
        ('except LookupError:', 'raise KeyError', []),
        ('except (OSError, KeyError):', 'raise KeyError', []),
        ('except:', 'raise ValueError', []),
        ('except Exception:', 'raise errors.Foo()', []),
        ('except BaseException:', 'raise KeyboardInterrupt', []),
        ('except Exception:', 'raise KeyboardInterrupt', ['KeyboardInterrupt']),
        ('except ValueError:', 'raise KeyError()', ['KeyError']),
        ('except ValueError:', 'raise errors.Foo()', ['errors.Foo']),
        ])
def test_raise_caught_by_its_handler_is_dropped(handler, raised, expected):
    """Verify a raise in a try body is listed only when no handler catches it.

    Mutation: no try filtering (lists every caught raise), exact-name
    matching only (keeps KeyError under LookupError), or Exception
    catching every builtin (drops KeyboardInterrupt).
    Oracle: Python's except semantics on the builtin class hierarchy.
    """
    source = (
        'def f():\n'
        '    try:\n'
        f'        {raised}\n'
        f'    {handler}\n'
        '        pass\n')
    assert raises_of(source) == expected


def test_handler_reraise_lists_the_caught_types():
    """Verify `raise` and `raise err` in a handler list what it caught.

    Mutation: ignoring a bare raise, or not mapping the handler's `as`
    name back to its types.
    Oracle: each handler re-raises exactly the classes it names.
    """
    source = (
        'def f():\n'
        '    try:\n'
        '        g()\n'
        '    except KeyError as err:\n'
        '        raise err\n'
        '    except (OSError, ValueError):\n'
        '        raise\n')
    assert raises_of(source) == ['KeyError', 'OSError', 'ValueError']


def test_raises_outside_the_try_body_are_kept():
    """Verify raises in a handler, else and finally are never filtered.

    Mutation: filtering every raise inside the try statement, which drops
    the else branch's ValueError because the handler names ValueError.
    Oracle: only the try body runs under the handlers.
    """
    source = (
        'def f():\n'
        '    try:\n'
        '        g()\n'
        '    except ValueError:\n'
        '        raise TypeError()\n'
        '    else:\n'
        '        raise ValueError()\n'
        '    finally:\n'
        '        raise OSError()\n')
    assert raises_of(source) == ['TypeError', 'ValueError', 'OSError']


@pytest.mark.parametrize(
    ('body', 'handler', 'expected'),
    [
        (
            'raise BadZipFile("x")',
            'except:\n        close()\n        raise',
            ['BadZipFile'],
            ),
        (
            'raise ValueError',
            'except Exception:\n        log()\n        raise',
            ['ValueError'],
            ),
        (
            'raise KeyError',
            'except BaseException as e:\n        raise e',
            ['KeyError'],
            ),
        ])
def test_handler_reraise_keeps_the_caught_body_class(body, handler, expected):
    """Verify a re-raising handler lists the body raise it caught.

    Mutation: listing the handler's own types on re-raise, which gives
    [] for a bare except and Exception or BaseException for the others.
    Oracle: the re-raise propagates exactly the class the body raised.
    """
    source = f'def f(fp):\n    try:\n        {body}\n    {handler}\n'
    assert raises_of(source) == expected


def test_underscore_classes_count_and_all_caps_constants_do_not():
    """Verify _Private classes are listed and an ALL_CAPS handler type is not.

    Mutation: testing the first character without stripping underscores
    (drops _GiveupOnFastCopy), dropping the all-caps check (lists
    TEST_OUTCOME), or applying it to one letter (drops E).
    Oracle: PEP 8 names classes in CapWords and constants in all caps.
    """
    source = (
        'def f():\n'
        '    raise _GiveupOnFastCopy(1)\n'
        '    raise __NotImplementedError\n'
        '    try:\n'
        '        g()\n'
        '    except TEST_OUTCOME:\n'
        '        raise\n'
        '    raise E(1)\n')
    assert raises_of(source) == ['_GiveupOnFastCopy', '__NotImplementedError', 'E']


def test_nested_handler_reraises_the_outer_handler_name():
    """Verify `raise e` names the outer handler's catch from an inner handler.

    Mutation: checking only the innermost handler for the `as` name, which
    drops KeyError.
    Oracle: e is bound to the KeyError the outer handler caught.
    """
    source = (
        'def f(a):\n'
        '    try:\n'
        '        raise KeyError(a)\n'
        '    except LookupError as e:\n'
        '        try:\n'
        '            g()\n'
        '        except OSError:\n'
        '            raise e\n')
    assert raises_of(source) == ['KeyError']


@pytest.mark.parametrize(
    ('signature', 'bound', 'expected'),
    [
        ('def f(self, /, a, *, key=None):', True, ['a', 'key']),
        ('def f(*args, key=None):', True, ['key']),
        ('def f(a, b, /, c):', False, ['a', 'b', 'c']),
        ])
def test_first_positional_argument_is_the_one_dropped(signature, bound, expected):
    """Verify only the first positional argument is dropped, if there is one.

    Mutation: popping the first entry of the merged list (drops key when
    there is no positional argument), or leaving out posonlyargs (drops
    a and b, or pops a in place of self).
    Oracle: Python binds the instance to the first positional parameter.
    """
    visitor = MethodVisitor(bound=bound)
    visitor.visit(ast.parse(f'{signature}\n    pass\n'))
    assert [argument['arg'] for argument in visitor.arguments] == expected
