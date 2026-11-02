import ast
import sys
from pathlib import Path
from typing import NamedTuple

EMPTY_CALLS = frozenset(
    {
        "list",
        "dict",
        "set",
        "tuple",
        "frozenset",
        "bytearray",
        "deque",
        "OrderedDict",
        "defaultdict",
        "Counter",
    }
)
COPY_CALLS = frozenset(
    {"list", "dict", "set", "tuple", "sorted", "deepcopy", "copy"}
)
COPY_METHOD = "copy"
EMPTY_LITERALS = (ast.List, ast.Tuple, ast.Set)
COPY_SOURCES = (ast.Name, ast.BoolOp)
LOOPS = (ast.For, ast.AsyncFor, ast.While)
EXITS = (ast.Break, ast.Return, ast.Raise, ast.Yield, ast.YieldFrom)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
BODY_ONLY = (
    ast.Module,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.With,
    ast.AsyncWith,
    ast.ExceptHandler,
    ast.match_case,
)
BODY_AND_ELSE = (ast.For, ast.AsyncFor, ast.While, ast.If)
WITH_FINALLY = (ast.Try, ast.TryStar)

type Loop = ast.For | ast.AsyncFor | ast.While
type Block = list[ast.stmt]


class Binding(NamedTuple):
    statement: ast.stmt
    name: str
    value: ast.expr


class LostUpdate(NamedTuple):
    path: str
    line_number: int
    reason: str


def called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id

    if isinstance(call.func, ast.Attribute):
        return call.func.attr

    return None


def is_empty_collection(expression: ast.expr) -> bool:
    if isinstance(expression, EMPTY_LITERALS):
        return not expression.elts

    if isinstance(expression, ast.Dict):
        return not expression.keys

    if isinstance(expression, ast.Call):
        is_bare = not expression.args and not expression.keywords
        return is_bare and called_name(expression) in EMPTY_CALLS

    return False


def copied_source(expression: ast.expr) -> ast.expr | None:
    if not isinstance(expression, ast.Call):
        return None

    source: ast.expr | None = None
    function = expression.func

    if len(expression.args) == 1 and called_name(expression) in COPY_CALLS:
        source = expression.args[0]
    elif isinstance(function, ast.Attribute) and not expression.args:
        source = function.value if function.attr == COPY_METHOD else None

    return source if isinstance(source, COPY_SOURCES) else None


def names_in(expression: ast.AST) -> set[str]:
    return {
        node.id for node in ast.walk(expression) if isinstance(node, ast.Name)
    }


def loaded_names(nodes: list[ast.stmt]) -> set[str]:
    loaded: set[str] = set()

    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loaded.add(node.id)

    return loaded


def stored_names(loop: Loop) -> set[str]:
    stored: set[str] = set()

    for node in ast.walk(loop):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            stored.add(node.id)

    return stored


def plain_binding(node: ast.AST) -> Binding | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]

        if isinstance(target, ast.Name):
            return Binding(node, target.id, node.value)

    if isinstance(node, ast.AnnAssign) and node.value is not None:
        target = node.target

        if isinstance(target, ast.Name):
            return Binding(node, target.id, node.value)

    return None


def blocks_of(node: ast.AST) -> list[Block]:
    if isinstance(node, BODY_ONLY):
        return [node.body]

    if isinstance(node, BODY_AND_ELSE):
        return [node.body, node.orelse]

    if isinstance(node, WITH_FINALLY):
        return [node.body, node.orelse, node.finalbody]

    return []


def bindings_inside(loop: Loop) -> dict[str, list[Binding]]:
    bindings: dict[str, list[Binding]] = {}
    pending: list[ast.AST] = list(ast.iter_child_nodes(loop))

    while pending:
        node = pending.pop()

        if isinstance(node, SCOPES):
            continue

        binding = plain_binding(node)

        if binding is not None:
            bindings.setdefault(binding.name, []).append(binding)

        pending.extend(ast.iter_child_nodes(node))

    return bindings


class LoopFacts:
    def __init__(self, loop: Loop) -> None:
        self.body: Block = loop.body
        self.read_names: set[str] = loaded_names([*loop.body, *loop.orelse])
        self.stored_names: set[str] = stored_names(loop)
        self.can_leave: bool = any(
            isinstance(node, EXITS) for node in ast.walk(loop)
        )
        self.bindings: dict[str, list[Binding]] = bindings_inside(loop)


class LoopsAhead:
    def __init__(self, size: int) -> None:
        self._next_use: dict[str, int] = {}
        self._last_read: dict[str, int] = {}
        self._loop: Loop | None = None
        self._loop_index: int = size
        self._size: int = size
        self.waiting: dict[Loop, list[Binding]] = {}

    def visit(self, index: int, statement: ast.stmt) -> None:
        binding = plain_binding(statement)

        if binding is not None:
            self._wait_for_loop(binding)

        for name in loaded_names([statement]):
            self._next_use[name] = index
            _ = self._last_read.setdefault(name, index)

        if binding is not None:
            self._next_use[binding.name] = index

        if isinstance(statement, LOOPS):
            self._loop = statement
            self._loop_index = index

    def _wait_for_loop(self, binding: Binding) -> None:
        if self._loop is None:
            return

        next_use = self._next_use.get(binding.name, self._size)
        last_read = self._last_read.get(binding.name, -1)

        if next_use >= self._loop_index and last_read > self._loop_index:
            self.waiting.setdefault(self._loop, []).append(binding)


def bindings_before_loops(block: Block) -> dict[Loop, list[Binding]]:
    loops_ahead = LoopsAhead(len(block))

    for index in reversed(range(len(block))):
        loops_ahead.visit(index, block[index])

    return loops_ahead.waiting


def is_replaced_result(
    binding: Binding, rebinding: Binding, facts: LoopFacts
) -> bool:
    is_top_level = any(
        statement is rebinding.statement for statement in facts.body
    )

    return (
        is_top_level
        and is_empty_collection(binding.value)
        and binding.name not in facts.read_names
        and not facts.can_leave
        and not is_empty_collection(rebinding.value)
    )


def is_rebuilt_copy(
    source: ast.expr, rebinding: Binding, facts: LoopFacts
) -> bool:
    source_names = names_in(source)

    if rebinding.name not in facts.read_names:
        return False

    if source_names & facts.stored_names:
        return False

    return bool(source_names & names_in(rebinding.value))


def replaced_reason(name: str) -> str:
    problem = f"{name} is replaced on every pass, so only the last is kept"
    return f"{problem} - add to {name} instead of replacing it"


def rebuilt_reason(name: str, source: ast.expr) -> str:
    problem = f"{name} is rebuilt from {ast.unparse(source)} on every pass"
    lost = "so the changes of earlier passes are lost"
    return f"{problem}, {lost} - build on {name} instead"


class LostUpdates:
    def __init__(self, path: str) -> None:
        self._path: str = path
        self.found: list[LostUpdate] = []

    def check(self, block: Block) -> None:
        for loop, bindings in bindings_before_loops(block).items():
            facts = LoopFacts(loop)

            for binding in bindings:
                self._check_binding(binding, facts)

    def _check_binding(self, binding: Binding, facts: LoopFacts) -> None:
        source = copied_source(binding.value)
        name = binding.name

        for rebinding in facts.bindings.get(name, []):
            if name in names_in(rebinding.value):
                continue

            if is_replaced_result(binding, rebinding, facts):
                self._add(rebinding, replaced_reason(name))

            if source is None:
                continue

            if is_rebuilt_copy(source, rebinding, facts):
                self._add(rebinding, rebuilt_reason(name, source))

    def _add(self, rebinding: Binding, reason: str) -> None:
        line_number = rebinding.statement.lineno
        self.found.append(LostUpdate(self._path, line_number, reason))


class LostLoopUpdates:
    def find_in(self, paths: list[str]) -> list[LostUpdate]:
        found: set[LostUpdate] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            updates = LostUpdates(path)

            for node in ast.walk(tree):
                for block in blocks_of(node):
                    updates.check(block)

            found.update(updates.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for lost in LostLoopUpdates().find_in(source_paths):
    _ = sys.stdout.write(f"{lost.path}:{lost.line_number}: {lost.reason}\n")
