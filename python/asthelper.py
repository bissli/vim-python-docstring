"""AST visitors that collect what a generated docstring lists.
"""
import ast
import builtins
from itertools import chain


class AttributeCollector(ast.NodeVisitor):
    """Attributes set on one name in an assignment target.

    Parameters
    ----------
    instance_name : str
        The name whose attributes count, e.g. self.

    Attributes
    ----------
    data : dict[str, None]
        Attribute names in visit order. For self.a.b only a counts.
    """

    def __init__(self, instance_name: str) -> None:
        self.instance_name = instance_name
        self.data = {}
        super().__init__()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Add node.attr to data when node is <instance_name>.attr.
        """
        if isinstance(node.value, ast.Name):
            if node.value.id == self.instance_name:
                self.data[node.attr] = None
        else:
            self.generic_visit(node)


class ClassInstanceNameExtractor(ast.NodeVisitor):
    """The name a class's methods give the instance.

    Attributes
    ----------
    instance_name : str
        The first argument of __init__, else of the last method, else
        'self'.
    set : bool
        True once __init__ has set instance_name.
    """

    def __init__(self) -> None:
        self.instance_name = 'self'
        self.set = False
        super().__init__()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Take node's first argument as instance_name unless __init__ set it.
        """
        if node.name == '__init__':
            self.instance_name = node.args.args[0].arg
            self.set = True
        elif not self.set:
            self.instance_name = node.args.args[0].arg

    def generic_visit(self, node: ast.AST) -> None:
        """Visit node's children until __init__ sets instance_name.
        """
        if not self.set:
            super().generic_visit(node)


class ClassVisitor(ast.NodeVisitor):
    """Instance attributes a class assigns anywhere in its body.

    Parameters
    ----------
    instance_name : str
        The instance's name, from `ClassInstanceNameExtractor`.

    Attributes
    ----------
    attributes : dict[str, None]
        Attribute names of instance_name that an assignment or annotated
        assignment target sets, in source order.
    """

    def __init__(self, instance_name: str) -> None:
        super().__init__()
        self.attributes = {}
        self.instance_name = instance_name

    def visit_Assign(self, node: ast.Assign) -> None:
        """Add the instance attributes that node's targets set.
        """
        ac = AttributeCollector(self.instance_name)
        for target in node.targets:
            ac.visit(target)
        self.attributes |= ac.data

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Add the instance attribute that node's target sets.
        """
        ac = AttributeCollector(self.instance_name)
        ac.visit(node.target)
        self.attributes |= ac.data


class MethodVisitor(ast.NodeVisitor):
    """What one function's docstring lists: arguments, raises, returns, yields.

    Parameters
    ----------
    parent : bool, default True
        False for a nested function. Only its raises merge into the
        enclosing function.
    bound : bool, default False
        True for a method that takes its instance or class first, so the
        first argument is dropped whatever its name. A first argument named
        self or cls is dropped either way.

    Attributes
    ----------
    arguments : list[dict]
        {'arg': name, 'type': annotation source or None} per positional-only,
        regular and keyword-only argument, with the first positional one
        dropped as `bound` says.
    raises : dict[str, None]
        Raised exception names as written, e.g. 'errors.Foo', in source order.
        A name whose last part, past leading underscores, starts lower case
        (err, self.error) counts as a variable, and an all-caps one longer
        than a letter (ERRORS) as a constant; both are left out. A raise
        that a handler of its `try` catches is left out unless the handler
        re-raises it.
    returns : bool
        True if the function has a return statement.
    yields : bool
        True if the function yields.
    """

    def __init__(self, parent: bool = True, bound: bool = False) -> None:
        self.parent = parent
        self.bound = bound
        self.arguments = []
        self.raises = {}
        self.returns = False
        self.yields = False
        self._handlers = []
        self._caught_by_handler = {}
        super().__init__()

    def _handle_functions(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Merge node's raises into this visitor's.

        Parameters
        ----------
        node : ast.FunctionDef or ast.AsyncFunctionDef
            A def met while visiting. A parent visitor also takes its
            arguments, returns and yields.
        """
        new_visitor = MethodVisitor(parent=False)
        new_visitor.generic_visit(node)
        self.raises |= new_visitor.raises

        if self.parent:
            positional = [*node.args.posonlyargs, *node.args.args]
            if positional and (self.bound or positional[0].arg in {'self', 'cls'}):
                positional.pop(0)
            for arg in chain(positional, node.args.kwonlyargs):
                type_hint = None
                if arg.annotation is not None:
                    type_hint = ast.unparse(arg.annotation)
                self.arguments.append({'arg': arg.arg, 'type': type_hint})

            self.returns = new_visitor.returns
            self.yields = new_visitor.yields

    def _raised_names(self, expr: ast.expr | None) -> list[str]:
        """Exception class names a raised expression can produce, as written.

        Parameters
        ----------
        expr : ast.expr or None
            The expression after `raise`, or a handler's caught type.

        Returns
        -------
        list[str]
            A call gives its callee, and `X(...).with_traceback(tb)` gives X.
            `a or B()` and `B() if c else C()` give each branch. Anything else,
            e.g. `make()()` or `errs[0]`, gives nothing.
        """
        if isinstance(expr, ast.BoolOp):
            return [name for value in expr.values for name in self._raised_names(value)]
        if isinstance(expr, ast.IfExp):
            return self._raised_names(expr.body) + self._raised_names(expr.orelse)
        if isinstance(expr, ast.Call):
            callee = expr.func
            if isinstance(callee, ast.Attribute) and callee.attr == 'with_traceback':
                return self._raised_names(callee.value)
            expr = callee
        root = expr
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return []
        last_part = expr.attr if isinstance(expr, ast.Attribute) else expr.id
        last_part = last_part.lstrip('_')
        is_constant = len(last_part) > 1 and last_part.isupper()
        is_class_name = last_part[:1].isupper() and not is_constant
        return [ast.unparse(expr)] if is_class_name else []

    def _handler_types(self, handler: ast.ExceptHandler) -> list[str]:
        """Class names an except clause catches; empty for a bare `except:`.
        """
        if isinstance(handler.type, ast.Tuple):
            return [
                name for elt in handler.type.elts for name in self._raised_names(elt)
                ]
        return self._raised_names(handler.type)

    def _catches(self, handler: ast.ExceptHandler, name: str) -> bool:
        """True if handler catches the exception class written as name.

        Parameters
        ----------
        handler : ast.ExceptHandler
            One except clause.
        name : str
            A name from `_raised_names`.

        Returns
        -------
        bool
            A bare `except:` catches all. Two builtin classes match by
            subclass, so LookupError catches KeyError. A name that is not a
            builtin class counts as an Exception subclass, so Exception and
            BaseException catch it. Otherwise only the exact name matches.
        """
        if handler.type is None:
            return True
        raised_class = getattr(builtins, name, None)
        for caught_name in self._handler_types(handler):
            caught_class = getattr(builtins, caught_name, None)
            if isinstance(raised_class, type) and isinstance(caught_class, type):
                if issubclass(raised_class, caught_class):
                    return True
            elif caught_name in {name, 'Exception', 'BaseException'}:
                return True
        return False

    def visit_Raise(self, node: ast.Raise) -> None:
        """Add the classes node raises, or what a handler re-raises.
        """
        if node.exc is None:
            handler = self._handlers[-1] if self._handlers else None
        elif isinstance(node.exc, ast.Name):
            handler = next(
                (h for h in reversed(self._handlers) if h.name == node.exc.id), None)
        else:
            handler = None
        if handler is not None:
            raised_names = (
                self._caught_by_handler.get(handler) or self._handler_types(handler))
        else:
            raised_names = self._raised_names(node.exc)
        for name in raised_names:
            self.raises[name] = None
        super().generic_visit(node)

    def visit_Try(self, node: ast.Try | ast.TryStar) -> None:
        """Drop body raises a handler catches, keeping them for its re-raise.
        """
        enclosing_raises, self.raises = self.raises, {}
        for statement in node.body:
            self.visit(statement)
        body_raises, self.raises = self.raises, enclosing_raises
        for name in body_raises:
            handler = next((h for h in node.handlers if self._catches(h, name)), None)
            if handler is None:
                self.raises[name] = None
            else:
                self._caught_by_handler.setdefault(handler, []).append(name)
        for statement in [*node.handlers, *node.orelse, *node.finalbody]:
            self.visit(statement)

    visit_TryStar = visit_Try

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Visit node's body with node as the innermost open handler.
        """
        self._handlers.append(node)
        super().generic_visit(node)
        self._handlers.pop()

    def visit_Yield(self, node: ast.Yield) -> None:
        """Mark the function as a generator.
        """
        self.yields = True
        super().generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        """Mark the function as returning, bare `return` included.
        """
        self.returns = True
        super().generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Merge in a def as `_handle_functions` says.
        """
        self._handle_functions(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Merge in an async def as `_handle_functions` says.
        """
        self._handle_functions(node)
