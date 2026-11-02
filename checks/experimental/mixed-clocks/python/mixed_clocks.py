import ast
import sys
from pathlib import Path
from typing import NamedTuple, override

NESTING_LIMIT = 100_000

WALL = "wall"
MONOTONIC = "monotonic"
PERFORMANCE = "perf_counter"
PROCESS = "process_time"
THREAD = "thread_time"
EVENT_LOOP = "event loop"
MIXED = "mixed"
CLOCKS = frozenset({WALL, MONOTONIC, PERFORMANCE, PROCESS, THREAD})
UNCERTAIN = frozenset({MIXED, EVENT_LOOP})
CLOCK_CALLS = {
    "time.time": WALL,
    "time.time_ns": WALL,
    "time.monotonic": MONOTONIC,
    "time.monotonic_ns": MONOTONIC,
    "time.perf_counter": PERFORMANCE,
    "time.perf_counter_ns": PERFORMANCE,
    "time.process_time": PROCESS,
    "time.process_time_ns": PROCESS,
    "time.thread_time": THREAD,
    "time.thread_time_ns": THREAD,
}
EVENT_LOOP_CALLS = frozenset(
    {
        "asyncio.get_running_loop",
        "asyncio.get_event_loop",
        "asyncio.new_event_loop",
    }
)
EVENT_LOOP_TYPE = "AbstractEventLoop"
EVENT_LOOP_CLOCK = "time"
NOW_CALLS = frozenset(
    {
        "datetime.datetime.now",
        "datetime.datetime.utcnow",
        "datetime.datetime.today",
    }
)
TIMESTAMP_METHOD = "timestamp"
NUMBER_CASTS = frozenset({"int", "float", "round"})
ORDERINGS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
SCALINGS = (ast.Mult, ast.Div, ast.FloorDiv)
SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type Attributes = dict[str, Origin]


class Origin(NamedTuple):
    clock: str
    line_number: int


class ClockMismatch(NamedTuple):
    path: str
    line_number: int
    left: str
    left_clock: str
    right: str
    right_clock: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return f"{dotted_name(expression.value)}.{expression.attr}"

    return ""


def import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is not None:
                    aliases[alias.asname] = alias.name

        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                bound_name = alias.asname or alias.name
                aliases[bound_name] = f"{node.module}.{alias.name}"

    return aliases


def stored_names(function: FunctionNode) -> frozenset[str]:
    arguments = function.args
    parameters = [*arguments.posonlyargs, *arguments.args]
    parameters.extend(arguments.kwonlyargs)
    names = {parameter.arg for parameter in parameters}
    pending: list[ast.AST] = list(function.body)

    while pending:
        node = pending.pop()

        if isinstance(node, SCOPE_NODES):
            continue

        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)

        pending.extend(ast.iter_child_nodes(node))

    return frozenset(names)


def is_none(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is None


def is_duration_constant(expression: ast.expr) -> bool:
    if isinstance(expression, ast.Constant):
        return isinstance(expression.value, int | float)

    return dotted_name(expression).rpartition(".")[2].isupper()


def merged(first: Origin | None, second: Origin) -> Origin:
    if first is None:
        return second

    if first.clock == second.clock:
        return first

    return Origin(MIXED, first.line_number)


class Scope:
    def __init__(
        self,
        parent: "Scope | None",
        bound_names: frozenset[str],
        receiver: str | None,
        attributes: Attributes,
    ) -> None:
        self._parent: Scope | None = parent
        self._bound_names: frozenset[str] = bound_names
        self._origins: dict[str, Origin] = {}
        self.receiver: str | None = receiver
        self.attributes: Attributes = attributes

    def remember(self, name: str, origin: Origin) -> None:
        self._origins[name] = merged(self._origins.get(name), origin)

    def origin_of(self, name: str) -> Origin | None:
        if name in self._origins:
            return self._origins[name]

        if name in self._bound_names or self._parent is None:
            return None

        return self._parent.origin_of(name)

    def remember_attribute(self, name: str, origin: Origin) -> None:
        self.attributes[name] = merged(self.attributes.get(name), origin)

    def attribute_origin(self, attribute: ast.Attribute) -> Origin | None:
        receiver = attribute.value

        if not isinstance(receiver, ast.Name) or self.receiver is None:
            return None

        if receiver.id != self.receiver:
            return None

        return self.attributes.get(attribute.attr)

    def tracked_origin(self, expression: ast.expr) -> Origin | None:
        if isinstance(expression, ast.Name):
            return self.origin_of(expression.id)

        if isinstance(expression, ast.Attribute):
            return self.attribute_origin(expression)

        return None


class ClockReader:
    def __init__(self, aliases: dict[str, str]) -> None:
        self._aliases: dict[str, str] = aliases

    def clock_of(self, expression: ast.expr, scope: Scope) -> str | None:
        if isinstance(expression, ast.Call):
            return self._call_clock(expression, scope)

        if isinstance(expression, ast.BinOp):
            return self._operation_clock(expression, scope)

        if isinstance(expression, ast.UnaryOp):
            return self.clock_of(expression.operand, scope)

        if isinstance(expression, ast.IfExp):
            return self._choice_clock(expression, scope)

        origin = scope.tracked_origin(expression)
        return None if origin is None else origin.clock

    def is_clock_reading(self, expression: ast.expr, scope: Scope) -> bool:
        if not isinstance(expression, ast.Call):
            return False

        return self._call_clock(expression, scope) in CLOCKS

    def _qualified_name(self, expression: ast.expr) -> str:
        head, dot, rest = dotted_name(expression).partition(".")
        return self._aliases.get(head, head) + dot + rest

    def _call_clock(self, call: ast.Call, scope: Scope) -> str | None:
        callee = self._qualified_name(call.func)

        if callee in CLOCK_CALLS:
            return CLOCK_CALLS[callee]

        if callee in EVENT_LOOP_CALLS:
            return EVENT_LOOP

        if callee in NUMBER_CASTS and call.args:
            return self.clock_of(call.args[0], scope)

        if isinstance(call.func, ast.Attribute):
            return self._method_clock(call.func, scope)

        return None

    def _method_clock(
        self, method: ast.Attribute, scope: Scope
    ) -> str | None:
        receiver = method.value

        if method.attr == EVENT_LOOP_CLOCK:
            receiver_clock = self.clock_of(receiver, scope)
            return MONOTONIC if receiver_clock == EVENT_LOOP else None

        if method.attr != TIMESTAMP_METHOD:
            return None

        if not isinstance(receiver, ast.Call):
            return None

        if self._qualified_name(receiver.func) in NOW_CALLS:
            return WALL

        return None

    def _operation_clock(
        self, operation: ast.BinOp, scope: Scope
    ) -> str | None:
        left = self.clock_of(operation.left, scope)
        right = self.clock_of(operation.right, scope)

        if isinstance(operation.op, ast.Add):
            return self._sum_clock(left, right)

        if isinstance(operation.op, ast.Sub):
            return self._difference_clock(left, right, operation.right)

        if isinstance(operation.op, SCALINGS) and right is None:
            return left

        if isinstance(operation.op, ast.Mult) and left is None:
            return right

        return None

    @staticmethod
    def _sum_clock(left: str | None, right: str | None) -> str | None:
        if left in UNCERTAIN or right in UNCERTAIN:
            return MIXED

        if left is None:
            return right

        if right is None:
            return left

        return MIXED

    @staticmethod
    def _difference_clock(
        left: str | None, right: str | None, subtrahend: ast.expr
    ) -> str | None:
        if left in UNCERTAIN or right in UNCERTAIN:
            return MIXED

        if left is None:
            return None

        if right is None:
            return left if is_duration_constant(subtrahend) else None

        return None if left == right else MIXED

    def _choice_clock(self, choice: ast.IfExp, scope: Scope) -> str | None:
        clocks: set[str | None] = set()

        for branch in (choice.body, choice.orelse):
            if not is_none(branch):
                clocks.add(self.clock_of(branch, scope))

        if len(clocks) == 1:
            return clocks.pop()

        return MIXED if clocks - {None} else None


class Comparison(NamedTuple):
    left: ast.expr
    right: ast.expr
    line_number: int
    scope: Scope


class ClassFrame(NamedTuple):
    attributes: Attributes
    scope_depth: int


class ClockVisitor(ast.NodeVisitor):
    def __init__(self, reader: ClockReader) -> None:
        self._reader: ClockReader = reader
        self._scopes: list[Scope] = [Scope(None, frozenset(), None, {})]
        self._classes: list[ClassFrame] = []
        self.comparisons: list[Comparison] = []

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._classes.append(ClassFrame({}, len(self._scopes)))
        self.generic_visit(node)
        _ = self._classes.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)

        for target in node.targets:
            self._remember(target, node.value)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)

        if node.value is not None:
            self._remember(node.target, node.value)

    @override
    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.generic_visit(node)
        self._remember(node.target, node.value)

    @override
    def visit_Compare(self, node: ast.Compare) -> None:
        left = node.left

        for operator, right in zip(node.ops, node.comparators, strict=True):
            if isinstance(operator, ORDERINGS):
                self._compare(left, right, node.lineno)

            left = right

        self.generic_visit(node)

    @override
    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Sub) and not self._is_offset(node):
            self._compare(node.left, node.right, node.lineno)

        self.generic_visit(node)

    def _visit_function(self, node: FunctionNode) -> None:
        scope = self._function_scope(node)
        self._remember_event_loop_parameters(node, scope)
        self._scopes.append(scope)
        self.generic_visit(node)
        _ = self._scopes.pop()

    def _function_scope(self, node: FunctionNode) -> Scope:
        parent = self._scopes[-1]
        receiver = parent.receiver
        attributes = parent.attributes

        if self._in_class_body():
            parameters = [*node.args.posonlyargs, *node.args.args]
            receiver = parameters[0].arg if parameters else None
            attributes = self._classes[-1].attributes

        return Scope(parent, stored_names(node), receiver, attributes)

    @staticmethod
    def _remember_event_loop_parameters(
        node: FunctionNode, scope: Scope
    ) -> None:
        arguments = node.args
        parameters = [*arguments.posonlyargs, *arguments.args]
        parameters.extend(arguments.kwonlyargs)

        for parameter in parameters:
            if parameter.annotation is None:
                continue

            type_name = dotted_name(parameter.annotation)

            if type_name.rpartition(".")[2] == EVENT_LOOP_TYPE:
                origin = Origin(EVENT_LOOP, node.lineno)
                scope.remember(parameter.arg, origin)

    def _in_class_body(self) -> bool:
        if not self._classes:
            return False

        return self._classes[-1].scope_depth == len(self._scopes)

    def _remember(self, target: ast.expr, value: ast.expr) -> None:
        scope = self._scopes[-1]
        clock = self._reader.clock_of(value, scope)

        if clock is None or self._in_class_body():
            return

        origin = Origin(clock, value.lineno)

        if isinstance(target, ast.Name):
            scope.remember(target.id, origin)

        if not isinstance(target, ast.Attribute):
            return

        owner = target.value

        if isinstance(owner, ast.Name) and owner.id == scope.receiver:
            scope.remember_attribute(target.attr, origin)

    def _is_offset(self, difference: ast.BinOp) -> bool:
        scope = self._scopes[-1]
        left = self._reader.is_clock_reading(difference.left, scope)
        right = self._reader.is_clock_reading(difference.right, scope)
        return left and right

    def _compare(
        self, left: ast.expr, right: ast.expr, line_number: int
    ) -> None:
        comparison = Comparison(left, right, line_number, self._scopes[-1])
        self.comparisons.append(comparison)


def described(expression: ast.expr, scope: Scope) -> str:
    text = ast.unparse(expression)
    origin = scope.tracked_origin(expression)

    if origin is None:
        return text

    return f"{text} (set on line {origin.line_number})"


class MixedClocks:
    def find_in(self, paths: list[str]) -> list[ClockMismatch]:
        found: set[ClockMismatch] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            reader = ClockReader(import_aliases(tree))
            visitor = ClockVisitor(reader)
            visitor.visit(tree)

            for comparison in visitor.comparisons:
                mismatch = self._mismatch(path, reader, comparison)

                if mismatch is not None:
                    found.add(mismatch)

        return sorted(found)

    @staticmethod
    def _mismatch(
        path: str, reader: ClockReader, comparison: Comparison
    ) -> ClockMismatch | None:
        scope = comparison.scope
        left_clock = reader.clock_of(comparison.left, scope)
        right_clock = reader.clock_of(comparison.right, scope)

        if left_clock not in CLOCKS or right_clock not in CLOCKS:
            return None

        if left_clock == right_clock:
            return None

        return ClockMismatch(
            path,
            comparison.line_number,
            described(comparison.left, scope),
            left_clock,
            described(comparison.right, scope),
            right_clock,
        )


sys.setrecursionlimit(NESTING_LIMIT)
source_paths = [line for line in sys.stdin.read().split("\n") if line]

for mismatch in MixedClocks().find_in(source_paths):
    location = f"{mismatch.path}:{mismatch.line_number}"
    left = f"{mismatch.left} is on the {mismatch.left_clock} clock"
    right = f"{mismatch.right} is on the {mismatch.right_clock} clock"
    advice = "read both from the same clock"
    _ = sys.stdout.write(f"{location}: {left} but {right} - {advice}\n")
