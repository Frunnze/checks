import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

LOCK_WORDS = frozenset(
    {"lock", "locks", "rlock", "rwlock", "mutex", "semaphore"}
)
TEST_NODES = (ast.If, ast.While, ast.Match)
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type Position = tuple[int, int]
type Assignment = ast.Assign | ast.AnnAssign


class LazyValue(NamedTuple):
    holder: str
    key: str | None


class LockedBlock(NamedTuple):
    line_number: int
    lock: ast.expr
    body: list[ast.stmt]


class Race(NamedTuple):
    path: str
    line_number: int
    value: str
    lock: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return f"{dotted_name(expression.value)}.{expression.attr}"

    if isinstance(expression, ast.Call):
        return dotted_name(expression.func)

    if isinstance(expression, ast.Subscript):
        return dotted_name(expression.value)

    return ""


def is_lock(expression: ast.expr) -> bool:
    last_name = dotted_name(expression).rpartition(".")[2]
    words = [word for word in WORD_BOUNDARY.split(last_name) if word]

    return bool(words) and words[-1].lower() in LOCK_WORDS


def locked_block(node: ast.AST) -> LockedBlock | None:
    if not isinstance(node, ast.With | ast.AsyncWith):
        return None

    for item in node.items:
        if is_lock(item.context_expr):
            return LockedBlock(node.lineno, item.context_expr, node.body)

    return None


def outer_locked_blocks(statements: list[ast.stmt]) -> list[LockedBlock]:
    found: list[LockedBlock] = []
    pending: list[ast.AST] = list(statements)

    while pending:
        node = pending.pop()
        locked = locked_block(node)

        if locked is not None:
            found.append(locked)
        elif not isinstance(node, SCOPE_NODES):
            pending.extend(ast.iter_child_nodes(node))

    return found


def nodes_in(statements: list[ast.stmt]) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending: list[ast.AST] = list(statements)

    while pending:
        node = pending.pop()
        found.append(node)

        if not isinstance(node, SCOPE_NODES):
            pending.extend(ast.iter_child_nodes(node))

    return found


def child_blocks(node: ast.AST) -> list[list[ast.stmt]]:
    if isinstance(node, ast.If | ast.For | ast.AsyncFor | ast.While):
        return [node.body, node.orelse]

    if isinstance(node, ast.Try | ast.TryStar):
        return [node.body, node.orelse, node.finalbody]

    if isinstance(
        node, ast.With | ast.AsyncWith | ast.ExceptHandler | ast.match_case
    ):
        return [node.body]

    return []


def blocks_in(function: FunctionNode) -> Iterator[list[ast.stmt]]:
    yield function.body

    for node in nodes_in(function.body):
        yield from child_blocks(node)


def bound_names(function: FunctionNode) -> set[str]:
    arguments = function.args
    every_argument = [
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
        *([arguments.vararg] if arguments.vararg else []),
        *([arguments.kwarg] if arguments.kwarg else []),
    ]
    bound = {argument.arg for argument in every_argument}
    declared: set[str] = set()

    for node in nodes_in(function.body):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)

        if isinstance(node, ast.Global | ast.Nonlocal):
            declared.update(node.names)

    return bound - declared


class LazyValues:
    def __init__(self, local_names: set[str]) -> None:
        self._local_names: set[str] = local_names

    def unset_in(self, test: ast.expr) -> list[LazyValue]:
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            found: list[LazyValue] = []

            for operand in test.values:
                found.extend(self.unset_in(operand))

            return found

        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return self._shared(test.operand, None)

        return self._compared(test, ast.Is, ast.NotIn)

    def set_in(self, test: ast.expr) -> list[LazyValue]:
        if isinstance(test, ast.Name | ast.Attribute):
            return self._shared(test, None)

        return self._compared(test, ast.IsNot, ast.In)

    def _compared(
        self,
        test: ast.expr,
        none_operator: type[ast.cmpop],
        member_operator: type[ast.cmpop],
    ) -> list[LazyValue]:
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            return []

        operator = test.ops[0]
        right = test.comparators[0]

        if isinstance(operator, none_operator) and is_none(right):
            return self._shared(test.left, None)

        if isinstance(operator, member_operator):
            return self._shared(right, ast.unparse(test.left))

        return []

    def _shared(self, holder: ast.expr, key: str | None) -> list[LazyValue]:
        if isinstance(holder, ast.Attribute):
            return [LazyValue(ast.unparse(holder), key)]

        if isinstance(holder, ast.Name) and holder.id not in self._local_names:
            return [LazyValue(holder.id, key)]

        return []


def is_none(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is None


def position(node: ast.expr | ast.stmt) -> Position:
    return (node.lineno, node.col_offset)


def assignment_targets(node: Assignment) -> list[ast.expr]:
    if isinstance(node, ast.AnnAssign):
        return [node.target]

    targets: list[ast.expr] = []

    for target in node.targets:
        if isinstance(target, ast.Tuple | ast.List):
            targets.extend(target.elts)
        else:
            targets.append(target)

    return targets


def is_target_of(target: ast.expr, value: LazyValue) -> bool:
    if value.key is None:
        return ast.unparse(target) == value.holder

    if not isinstance(target, ast.Subscript):
        return False

    holder = ast.unparse(target.value)
    return holder == value.holder and ast.unparse(target.slice) == value.key


def first_creation(
    locked: LockedBlock, value: LazyValue
) -> Assignment | None:
    creations: list[Assignment] = []

    for node in nodes_in(locked.body):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue

        if node.value is None or isinstance(node.value, ast.Constant):
            continue

        targets = assignment_targets(node)

        if any(is_target_of(target, value) for target in targets):
            creations.append(node)

    return min(creations, key=position, default=None)


def tests_before(locked: LockedBlock, assignment: Assignment) -> bool:
    start = position(assignment)

    for node in nodes_in(locked.body):
        if isinstance(node, TEST_NODES) and position(node) < start:
            return True

    return False


def reads_in_value(assignment: Assignment, value: LazyValue) -> bool:
    if assignment.value is None:
        return False

    for node in ast.walk(assignment.value):
        is_read = isinstance(node, ast.Name | ast.Attribute)

        if is_read and ast.unparse(node) == value.holder:
            return True

    return False


def race_in(locked: LockedBlock, value: LazyValue) -> bool:
    assignment = first_creation(locked, value)

    if assignment is None or tests_before(locked, assignment):
        return False

    return not reads_in_value(assignment, value)


def returns_early(statement: ast.If) -> bool:
    return not statement.orelse and isinstance(statement.body[-1], ast.Return)


class Races:
    def __init__(self, path: str) -> None:
        self._path: str = path
        self.found: list[Race] = []

    def check(self, function: FunctionNode) -> None:
        lazy_values = LazyValues(bound_names(function))

        for block in blocks_in(function):
            self._check_block(block, lazy_values)

    def _check_block(
        self, block: list[ast.stmt], lazy_values: LazyValues
    ) -> None:
        for index, statement in enumerate(block):
            if not isinstance(statement, ast.If):
                continue

            for value in lazy_values.unset_in(statement.test):
                self._check_locks(statement.body, value)

            if returns_early(statement):
                for value in lazy_values.set_in(statement.test):
                    self._check_locks(block[index + 1:], value)

    def _check_locks(
        self, statements: list[ast.stmt], value: LazyValue
    ) -> None:
        for locked in outer_locked_blocks(statements):
            if race_in(locked, value):
                self._report(locked, value)

    def _report(self, locked: LockedBlock, value: LazyValue) -> None:
        lock = ast.unparse(locked.lock)
        self.found.append(
            Race(self._path, locked.line_number, value.holder, lock)
        )


class LazyInitializationRaces:
    def find_in(self, paths: list[str]) -> list[Race]:
        found: set[Race] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            races = Races(path)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    races.check(node)

            found.update(races.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for race in LazyInitializationRaces().find_in(source_paths):
    location = f"{race.path}:{race.line_number}"
    problem = (
        f"{race.value} is tested before taking {race.lock} but set under"
        " it without a second test, so two callers can both set it"
    )
    fix = f"test {race.value} again inside the lock before setting it"
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
