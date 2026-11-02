import ast
import sys
from pathlib import Path
from typing import NamedTuple

EXITS = (ast.Break, ast.Return, ast.Raise)
UNSCANNED = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.Try,
    ast.Match,
    ast.Yield,
    ast.YieldFrom,
    ast.Await,
    ast.Global,
    ast.Nonlocal,
)
CONDITION_NODES = (
    ast.Name,
    ast.Constant,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.expr_context,
    ast.cmpop,
    ast.boolop,
    ast.unaryop,
    ast.operator,
)
SIZE_CALL = "len"
STORES = (ast.Store, ast.Del)
PURE_CALLS = frozenset(
    {
        "len",
        "isinstance",
        "str",
        "int",
        "float",
        "bool",
        "abs",
        "min",
        "max",
        "round",
        "get",
        "startswith",
        "endswith",
        "strip",
        "lower",
        "upper",
        "split",
        "keys",
        "values",
        "items",
    }
)
SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)


class StalledLoop(NamedTuple):
    path: str
    line_number: int
    loop_line: int


def is_size_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == SIZE_CALL
    )


def condition_names(test: ast.expr) -> set[str]:
    names: set[str] = set()

    for node in ast.walk(test):
        if is_size_call(node) or (
            isinstance(node, ast.Name) and node.id == SIZE_CALL
        ):
            continue

        if not isinstance(node, CONDITION_NODES):
            return set()

        if isinstance(node, ast.Name):
            names.add(node.id)

    return names


def called_name(call: ast.Call) -> str:
    function = call.func

    if isinstance(function, ast.Attribute):
        return function.attr

    return function.id if isinstance(function, ast.Name) else ""


class Progress:
    def __init__(self, carried: set[str]) -> None:
        self._carried: set[str] = carried

    def made_by(self, node: ast.AST) -> bool:
        return any(map(self._changes, ast.walk(node)))

    def _changes(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name) and isinstance(node.ctx, STORES):
            return node.id in self._carried

        if isinstance(node, ast.Subscript | ast.Attribute):
            return isinstance(node.ctx, STORES)

        if isinstance(node, ast.Call):
            return called_name(node) not in PURE_CALLS

        return isinstance(node, ast.AugAssign)


def stored_names(nodes: list[ast.AST]) -> set[str]:
    names: set[str] = set()

    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, STORES):
            names.add(node.id)

    return names


def carried_names(scope: ast.AST, loop: ast.While) -> set[str]:
    inside = {id(node) for node in ast.walk(loop)}
    outside = [
        node for node in ast.walk(scope) if id(node) not in inside
    ]
    names = stored_names(outside)

    if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
        arguments = scope.args
        everyone = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        ]
        names.update(argument.arg for argument in everyone)

    return names | condition_names(loop.test)


class LoopPaths:
    def __init__(self, progress: Progress) -> None:
        self._progress: Progress = progress
        self.stalled_lines: list[int] = []

    def scan(self, statements: list[ast.stmt], *, moved: bool) -> bool | None:
        for statement in statements:
            if isinstance(statement, ast.Continue):
                self._stall_unless(statement.lineno, moved=moved)
                return None

            if isinstance(statement, EXITS):
                return None

            if isinstance(statement, ast.If):
                after = self._scan_branches(statement, moved=moved)

                if after is None:
                    return None

                moved = after
            elif isinstance(statement, ast.With | ast.AsyncWith):
                items = [item.context_expr for item in statement.items]
                entered = moved or any(map(self._progress.made_by, items))
                after = self.scan(statement.body, moved=entered)

                if after is None:
                    return None

                moved = after
            else:
                moved = moved or self._progress.made_by(statement)

        return moved

    def _scan_branches(self, statement: ast.If, *, moved: bool) -> bool | None:
        tested = moved or self._progress.made_by(statement.test)
        body = self.scan(statement.body, moved=tested)
        orelse = self.scan(statement.orelse, moved=tested)

        if body is None and orelse is None:
            return None

        return (body is None or body) and (orelse is None or orelse)

    def _stall_unless(self, line_number: int, *, moved: bool) -> None:
        if not moved:
            self.stalled_lines.append(line_number)


def is_straight_line(statements: list[ast.stmt]) -> bool:
    branches = (ast.If, ast.With, ast.AsyncWith)

    return not any(isinstance(item, branches) for item in statements)


def has_unscanned_flow(loop: ast.While) -> bool:
    for statement in loop.body:
        for node in ast.walk(statement):
            if isinstance(node, UNSCANNED):
                return True

    return False


class StalledLoops:
    def find_in(self, paths: list[str]) -> list[StalledLoop]:
        found: set[StalledLoop] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for scope in ast.walk(tree):
                if isinstance(scope, SCOPES):
                    found.update(self._in_scope(path, scope))

        return sorted(found)

    def _in_scope(self, path: str, scope: ast.AST) -> list[StalledLoop]:
        found: list[StalledLoop] = []

        for node in own_nodes(scope):
            if isinstance(node, ast.While):
                found.extend(self._in_loop(path, scope, node))

        return found

    def _in_loop(
        self, path: str, scope: ast.AST, loop: ast.While
    ) -> list[StalledLoop]:
        if not condition_names(loop.test) or has_unscanned_flow(loop):
            return []

        progress = Progress(carried_names(scope, loop))
        paths = LoopPaths(progress)
        end_moved = paths.scan(loop.body, moved=False)
        lines = list(paths.stalled_lines)

        if end_moved is False and is_straight_line(loop.body):
            lines.append(loop.body[-1].lineno)

        return [StalledLoop(path, line, loop.lineno) for line in lines]


def own_nodes(scope: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(scope))

    while pending:
        node = pending.pop()
        found.append(node)

        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            pending.extend(ast.iter_child_nodes(node))

    return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for stalled in StalledLoops().find_in(source_paths):
    location = f"{stalled.path}:{stalled.line_number}"
    problem = f"this path returns to the loop test on line {stalled.loop_line}"
    reason = "without changing anything the test reads"
    _ = sys.stdout.write(f"{location}: {problem} {reason}\n")
