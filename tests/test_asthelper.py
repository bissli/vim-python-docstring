"""What the asthelper visitors collect from parsed source.
"""
import ast
import inspect

import pytest
from asthelper import ClassInstanceNameExtractor, ClassVisitor, MethodVisitor


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


@pytest.mark.parametrize(
    ('methods', 'expected'),
    [
        (
            ('    @staticmethod\n    def f():\n        pass\n'
             '    def run(self):\n        self.a = 1\n'),
            ['a'],
            ),
        (
            ('    def f():\n        pass\n'
             '    def run(self):\n        self.a = 1\n'),
            ['a'],
            ),
        ('    def __init__(this, /):\n        this.a = 1\n', ['a']),
        ('    def m(this, /, x):\n        this.a = x\n', ['a']),
        (
            ('    def set(self, v):\n        self.v = v\n'
             '    @staticmethod\n    def make(cfg):\n        cfg.port = 1\n'),
            ['v'],
            ),
        (
            ('    async def run(self):\n'
             '        def cb(item):\n            item.done = True\n'
             '        self.task = cb\n'),
            ['task'],
            ),
        ],
    ids=[
        'static-no-arg',
        'no-arg',
        'posonly-init',
        'posonly-method',
        'static-last',
        'async-nested-def',
        ])
def test_class_attributes_use_the_instance_argument(methods, expected):
    """Verify the class lists attributes of its methods' instance argument.

    Mutation: reading node.args.args[0] unguarded (IndexError on f() and
    on (this, /)), leaving out posonlyargs (takes x), letting a
    staticmethod set the name (takes cfg), or descending into an async
    def (takes item).
    Oracle: the observed `list index out of range` crash; README Features,
    a staticmethod's first argument is not its instance; Python binds the
    instance to the first positional parameter.
    """
    tree = ast.parse(f'class A:\n{methods}')
    extractor = ClassInstanceNameExtractor()
    extractor.visit(tree)
    visitor = ClassVisitor(extractor.instance_name)
    visitor.visit(tree)
    assert list(visitor.attributes) == expected


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        ('    yield from x\n', True),
        ('    def h():\n        yield from x\n    return h\n', False),
        ],
    ids=['top-level', 'nested-def'])
def test_yield_from_marks_only_its_own_function(body, expected):
    """Verify `yield from` makes its function a generator, not the outer one.

    Mutation: no visit_YieldFrom (the first case gives False), or a nested
    def's yields merged into its parent (the second case gives True).
    Oracle: Python's ast docs class YieldFrom with Yield as a yield
    expression, and a yield makes only its innermost def a generator.
    """
    visitor = MethodVisitor()
    visitor.visit(ast.parse(f'def g(x):\n{body}'))
    assert visitor.yields is expected


@pytest.mark.parametrize(
    'body',
    [
        '    return lambda: (yield x)\n',
        '    f = lambda: (yield from x)\n    return f\n',
        '    f = lambda y=(yield x): y\n    return f\n',
        ],
    ids=['lambda-yield', 'lambda-yield-from', 'lambda-default'])
def test_lambda_yield_marks_only_the_lambda(body):
    """Verify a yield in a lambda body leaves its def a plain function.

    Mutation: visiting the lambda body (the first two cases give True), or
    skipping the whole lambda (the default case gives False, though the
    def evaluates the default).
    Oracle: inspect.isgeneratorfunction on the same source.
    """
    source = f'def g(x):\n{body}'
    namespace = {}
    exec(source, namespace)
    visitor = MethodVisitor()
    visitor.visit(ast.parse(source))
    assert visitor.yields is inspect.isgeneratorfunction(namespace['g'])


@pytest.mark.parametrize(
    'body',
    [
        '    def h(x=(yield)):\n        pass\n    return h\n',
        '    def h(*, x=(yield)):\n        pass\n    return h\n',
        '    @(yield)\n    def h():\n        pass\n    return h\n',
        '    async def h(x=(yield)):\n        pass\n    return h\n',
        ],
    ids=['default', 'kw-default', 'decorator', 'async-default'])
def test_nested_def_header_yield_marks_the_outer_def(body):
    """Verify a yield in a nested def's default or decorator marks its parent.

    Mutation: visiting the nested def's defaults and decorators inside its
    own visitor (every case gives False).
    Oracle: inspect.isgeneratorfunction on the same source.
    """
    source = f'def g():\n{body}'
    namespace = {}
    exec(source, namespace)
    visitor = MethodVisitor()
    visitor.visit(ast.parse(source))
    assert visitor.yields is inspect.isgeneratorfunction(namespace['g'])


@pytest.mark.parametrize(
    'header',
    ['def h(x: (yield)):', 'def h() -> (yield):'],
    ids=['argument', 'return'])
def test_nested_def_annotation_yield_marks_the_outer_def(header):
    """Verify a yield in a nested def's annotation marks its parent.

    Mutation: visiting only the nested def's defaults and decorators in
    the parent (both cases give False).
    Oracle: Python 3.11 evaluates the annotations when the def runs, so
    inspect.isgeneratorfunction gives True there; 3.14 and the
    annotations future import reject the source, so no valid code differs.
    """
    visitor = MethodVisitor()
    visitor.visit(ast.parse(f'def g():\n    {header}\n        pass\n    return h\n'))
    assert visitor.yields is True


def class_attributes_of(source: str) -> list[str]:
    """Attribute names ClassController lists for the class in source.
    """
    tree = ast.parse(source)
    extractor = ClassInstanceNameExtractor()
    extractor.visit(tree)
    visitor = ClassVisitor(extractor.instance_name)
    visitor.visit(tree)
    return list(visitor.attributes)


def test_classmethod_first_argument_is_not_the_instance():
    """Verify a trailing classmethod leaves the instance name to the method.

    Mutation: letting a classmethod set the instance name (drops x).
    Oracle: Python binds the class, not the instance, to a classmethod's
    first parameter; README Features, a class docstring lists its
    attributes.
    """
    source = (
        'class A:\n'
        '    def run(self):\n'
        '        self.x = 1\n'
        '    @classmethod\n'
        '    def make(cls):\n'
        '        cls.count = 0\n')
    assert class_attributes_of(source) == ['x', 'count']


@pytest.mark.parametrize(
    ('method', 'expected'),
    [
        ('def __new__(cls):\n        return object.__new__(cls)', ['x']),
        ('def __init_subclass__(cls):\n        cls.reg = 1', ['x', 'reg']),
        ('def __class_getitem__(cls, item):\n        cls.reg = item', ['x', 'reg']),
        ],
    ids=['new', 'init-subclass', 'class-getitem'])
def test_implicit_class_first_methods_are_not_the_instance(method, expected):
    """Verify a trailing undecorated class-first method leaves the name alone.

    Mutation: checking only the staticmethod and classmethod decorators
    (instance name becomes cls, so the class lists [] or ['reg']), or
    leaving the dunders out of the class-first set (drops reg).
    Oracle: Python's data model docs make __new__ an implicit staticmethod
    taking the class, and __init_subclass__ and __class_getitem__ implicit
    classmethods.
    """
    source = (
        'class A:\n'
        '    def run(self):\n'
        '        self.x = 1\n'
        f'    {method}\n')
    assert class_attributes_of(source) == expected


@pytest.mark.parametrize(
    ('nested', 'expected'),
    [
        ('def cb(self):\n            self.y = 1\n', ['x']),
        ('def cb():\n            self.y = 1\n', ['y', 'x']),
        ('def cb(item, self=self):\n            self.y = item\n', ['y', 'x']),
        ('def cb(*, self=self):\n            self.y = 1\n', ['y', 'x']),
        ('def cb(self=None):\n            self.y = 1\n', ['x']),
        ],
    ids=['own-self', 'closure', 'default-self', 'kw-default-self', 'other-default'])
def test_nested_def_with_its_own_instance_name_is_skipped(nested, expected):
    """Verify a def in a method that rebinds self adds none of its attributes.

    Mutation: visiting every nested def (own-self lists y), skipping every
    nested def (closure drops y), ignoring a self=self default (the
    default-self cases drop y), or keeping any def with a self default
    (other-default lists y).
    Oracle: Python scoping, a parameter named self shadows the method's
    self, and a closure or a self=self default sets the method's instance.
    """
    source = (
        'class A:\n'
        '    def run(self):\n'
        f'        {nested}'
        '        self.x = cb\n')
    assert class_attributes_of(source) == expected


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        (
            ('    def run(self):\n        self.x = 1\n'
             '    class B:\n'
             '        def __init__(other):\n            other.b = 2\n'),
            ['x'],
            ),
        (
            ('    def __init__(self):\n        self.a = 1\n'
             '    class B:\n'
             '        def __init__(self):\n            self.b = 2\n'),
            ['a'],
            ),
        ],
    ids=['nested-init-name', 'nested-class-self'])
def test_nested_class_attributes_stay_out_of_the_outer_class(body, expected):
    """Verify a nested class sets neither the instance name nor attributes.

    Mutation: letting a nested __init__ set the instance name
    (nested-init-name drops x), or visiting a class nested in the class
    body (nested-class-self adds b).
    Oracle: README Features, a class docstring lists the class's
    attributes; a nested class's first parameter binds its own instance.
    """
    assert class_attributes_of(f'class A:\n{body}') == expected


@pytest.mark.parametrize(
    ('nested', 'expected'),
    [
        (
            ('class H:\n'
             '            def handle(inner):\n                self.last = inner\n'),
            ['last', 'h'],
            ),
        ('class H:\n            self.z = 1\n', ['z', 'h']),
        (
            ('class H:\n'
             '            def __init__(self):\n                self.y = 1\n'),
            ['h'],
            ),
        (
            ('class H:\n'
             '            def m(self=self):\n                self.k = 1\n'),
            ['h'],
            ),
        (
            ('class H:\n'
             '            @staticmethod\n'
             '            def m(self=self):\n                self.k = 1\n'),
            ['k', 'h'],
            ),
        (
            ('class H:\n'
             '            @builtins.staticmethod\n'
             '            def m(self=self):\n                self.k = 1\n'),
            ['k', 'h'],
            ),
        ],
    ids=[
        'method-closure',
        'class-body',
        'own-self-method',
        'method-self-default',
        'static-self-default',
        'qualified-static-self-default',
        ])
def test_class_in_method_sets_the_method_instance(nested, expected):
    """Verify a class defined in a method adds what it sets on self.

    Mutation: skipping every class met in a method (the first two cases
    drop last or z), visiting its methods as the outer class's own
    (own-self-method lists y), or letting a self=self default exempt a
    method's bound first parameter (method-self-default lists k), or
    matching only a bare staticmethod name (qualified-static-self-default
    drops k).
    Oracle: Python scoping, a class body and its methods see the
    enclosing method's self unless a parameter rebinds it, and H().m()
    binds H's instance to m's first parameter; running each source, then
    H().handle() or H().m(), sets exactly the expected names on A().
    """
    source = (
        'class A:\n'
        '    def run(self):\n'
        f'        {nested}'
        '        self.h = H\n')
    assert class_attributes_of(source) == expected


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        (
            ('    @builtins.classmethod\n'
             '    def make(klass):\n        klass.count = 0\n'
             '    def run(self):\n        self.x = 1\n'),
            ['count', 'x'],
            ),
        (
            ('    def run(self):\n'
             '        class H:\n'
             '            @classmethod\n'
             '            def m(cls):\n                cls.k = 1\n'
             '        self.h = H\n'),
            ['h'],
            ),
        (
            ('    def __new__(cls, n):\n'
             '        self = super().__new__(cls)\n'
             '        self._n = n\n'
             '        return self\n'),
            ['_n'],
            ),
        (
            ('    @classmethod\n'
             '    def make(cls):\n'
             '        def f(cls):\n            cls.y = 1\n'
             '        cls.count = f\n'),
            ['count'],
            ),
        (
            ('    def __init__(self):\n        pass\n'
             '    @classmethod\n'
             '    def make(cls):\n        cls.a, self.b = 1, 2\n'),
            ['a', 'b'],
            ),
        ],
    ids=[
        'qualified-then-instance',
        'class-in-method',
        'new-builds-self',
        'nested-def-own-cls',
        'one-target-both-names',
        ])
def test_classmethod_lists_what_it_sets_on_its_class(body, expected):
    """Verify a class-first method adds its first arg's attributes to self's.

    Mutation: matching only a bare classmethod name or a literal cls
    (qualified-then-instance drops count), counting the class name in a
    classmethod of a class defined in a method (class-in-method lists k),
    counting the class name in place of the instance name (new-builds-self
    drops _n), keeping it in a nested def with its own cls parameter
    (nested-def-own-cls lists y), or collecting one name at a time
    (one-target-both-names lists b first).
    Oracle: Python binds the class to a classmethod's first parameter
    whatever its name; H's classmethod sets H.k, never an attribute of A;
    Fraction.__new__ in the stdlib fractions module sets attributes on the
    self it builds; a parameter named cls shadows the classmethod's cls;
    the ClassVisitor docstring promises source order.
    """
    assert class_attributes_of(f'class A:\n{body}') == expected
