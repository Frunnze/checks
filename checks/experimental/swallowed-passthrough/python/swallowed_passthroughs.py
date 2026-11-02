import ast
import builtins
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple, override

NESTING_LIMIT = 100_000

BROAD_EXCEPTIONS = frozenset({"Exception", "BaseException"})
BASE_EXCEPTION = "BaseException"
BASE_ONLY_EXCEPTIONS = frozenset(
    {"KeyboardInterrupt", "SystemExit", "GeneratorExit", "CancelledError"}
)
BUILTIN_NAMES = frozenset(dir(builtins))
RECEIVER_NAMES = frozenset({"self", "cls"})
BARE_HANDLER = "a bare except"
MODULE_CODE = "module code"
CLASS_UNIT = "this class"
MODULE_UNIT = "this module"
KEEPING_NODES = (
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.NamedExpr,
    ast.Return,
    ast.Yield,
    ast.YieldFrom,
)
COMPOUND_STATEMENTS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.Match,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)
SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type UnitKey = tuple[str, int]


class Guard(NamedTuple):
    line_number: int
    function: str
    handler: str
    catches_base: bool
    passed: frozenset[str]
    covered: frozenset[str]
    swallows: bool
    collaborators: frozenset[str]


class Swallow(NamedTuple):
    path: str
    line_number: int
    handler: str
    missing: tuple[str, ...]
    functions: tuple[str, ...]
    unit: str


def last_name(dotted: str) -> str:
    return dotted.rpartition(".")[2]


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        receiver = dotted_name(expression.value)
        return f"{receiver}.{expression.attr}" if receiver else ""

    return ""


def exception_names(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return []

    if isinstance(handler.type, ast.Tuple):
        return [ast.unparse(element) for element in handler.type.elts]

    return [ast.unparse(handler.type)]


def is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True

    names = exception_names(handler)
    return any(name in BROAD_EXCEPTIONS for name in names)


def lets_through(handler: ast.ExceptHandler) -> bool:
    final_statement = handler.body[-1]
    return isinstance(final_statement, ast.Raise) and (
        final_statement.exc is None
    )


def own_nodes(statements: list[ast.stmt]) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending: list[ast.AST] = list(statements)

    while pending:
        node = pending.pop()

        if isinstance(node, SCOPE_NODES):
            continue

        found.append(node)
        pending.extend(ast.iter_child_nodes(node))

    return found


def re_raises(handler: ast.ExceptHandler) -> bool:
    nodes = own_nodes(handler.body)
    return any(isinstance(node, ast.Raise) for node in nodes)


def mentions(expression: ast.AST | None, name: str) -> bool:
    if expression is None:
        return False

    for node in ast.walk(expression):
        if isinstance(node, ast.Name) and node.id == name:
            return True

    return False


def keeps_exception(handler: ast.ExceptHandler) -> bool:
    if handler.name is None:
        return False

    for node in own_nodes(handler.body):
        if not isinstance(node, KEEPING_NODES):
            continue

        if mentions(node.value, handler.name):
            return True

    return False


def swallows(handler: ast.ExceptHandler) -> bool:
    return not re_raises(handler) and not keeps_exception(handler)


def collaborator(call: ast.Call) -> str:
    callee = call.func

    if isinstance(callee, ast.Name):
        return "" if callee.id in BUILTIN_NAMES else callee.id

    if not isinstance(callee, ast.Attribute):
        return ""

    receiver = dotted_name(callee.value)

    if receiver in RECEIVER_NAMES:
        return dotted_name(callee)

    return receiver


def collaborators(statements: list[ast.stmt]) -> frozenset[str]:
    names: set[str] = set()
    simple_statements: list[ast.stmt] = []

    for statement in statements:
        if not isinstance(statement, COMPOUND_STATEMENTS):
            simple_statements.append(statement)

    for node in own_nodes(simple_statements):
        if isinstance(node, ast.Call):
            names.add(collaborator(node))

    return frozenset(names - {""})


def handler_text(handler: ast.ExceptHandler) -> str:
    if handler.type is None:
        return BARE_HANDLER

    return f"except {ast.unparse(handler.type)}"


def catches_base(handler: ast.ExceptHandler) -> bool:
    names = exception_names(handler)
    return handler.type is None or BASE_EXCEPTION in map(last_name, names)


def guard_of(statement: ast.Try, function: str) -> Guard | None:
    for position, handler in enumerate(statement.handlers):
        if not is_broad(handler):
            continue

        earlier = statement.handlers[:position]
        passed: set[str] = set()
        covered: set[str] = set()

        for narrower in earlier:
            names = exception_names(narrower)
            covered.update(map(last_name, names))

            if lets_through(narrower):
                passed.update(names)

        return Guard(
            handler.lineno,
            function,
            handler_text(handler),
            catches_base(handler),
            frozenset(passed),
            frozenset(covered),
            swallows(handler),
            collaborators(statement.body),
        )

    return None


def is_missing(guard: Guard, name: str) -> bool:
    short_name = last_name(name)

    if short_name in guard.covered:
        return False

    return guard.catches_base or short_name not in BASE_ONLY_EXCEPTIONS


def is_sibling(passer: Guard, guard: Guard) -> bool:
    if not passer.passed or passer.function == guard.function:
        return False

    return bool(passer.collaborators & guard.collaborators)


class GuardVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self._units: list[UnitKey] = [(MODULE_UNIT, 0)]
        self._functions: list[str] = []
        self.guards: defaultdict[UnitKey, list[Guard]] = defaultdict(list)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._units.append((CLASS_UNIT, node.lineno))
        self.generic_visit(node)
        _ = self._units.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_Try(self, node: ast.Try) -> None:
        function = self._functions[-1] if self._functions else MODULE_CODE
        guard = guard_of(node, function)

        if guard is not None:
            self.guards[self._units[-1]].append(guard)

        self.generic_visit(node)

    def _visit_function(self, node: FunctionNode) -> None:
        self._functions.append(f"{node.name}()")
        self.generic_visit(node)
        _ = self._functions.pop()


class SwallowedPassthroughs:
    def find_in(self, paths: list[str]) -> list[Swallow]:
        found: set[Swallow] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            visitor = GuardVisitor()
            visitor.visit(tree)

            for (unit, _), guards in visitor.guards.items():
                for guard in guards:
                    swallow = self._swallow(path, unit, guard, guards)

                    if swallow is not None:
                        found.add(swallow)

        return sorted(found)

    @staticmethod
    def _swallow(
        path: str, unit: str, guard: Guard, guards: list[Guard]
    ) -> Swallow | None:
        if not guard.swallows or guard.passed:
            return None

        passers = [other for other in guards if is_sibling(other, guard)]

        if not passers:
            return None

        others = [passer.passed for passer in passers[1:]]
        agreed = passers[0].passed.intersection(*others)
        missing = sorted(name for name in agreed if is_missing(guard, name))

        if not missing:
            return None

        functions = sorted({passer.function for passer in passers})
        return Swallow(
            path,
            guard.line_number,
            guard.handler,
            tuple(missing),
            tuple(functions),
            unit,
        )


def described(swallow: Swallow) -> str:
    names = ", ".join(swallow.missing)
    caught = names if len(swallow.missing) == 1 else f"({names})"
    functions = ", ".join(swallow.functions)
    verb = "lets" if len(swallow.functions) == 1 else "let"
    passers = f"{functions} in {swallow.unit} {verb} through"
    fix = f'add "except {caught}: raise" above it'
    return f"{swallow.handler} swallows {names}, which {passers} - {fix}"


sys.setrecursionlimit(NESTING_LIMIT)
source_paths = [line for line in sys.stdin.read().split("\n") if line]

for found_swallow in SwallowedPassthroughs().find_in(source_paths):
    location = f"{found_swallow.path}:{found_swallow.line_number}"
    _ = sys.stdout.write(f"{location}: {described(found_swallow)}\n")
