import ast
import sys
from pathlib import Path
from typing import NamedTuple, cast

LOOPS = (ast.For, ast.AsyncFor, ast.While)
EXITS = (ast.Return, ast.Raise, ast.Break)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
OPTIONAL = "Optional"
COLLECTING_METHODS = frozenset(
    {"append", "extend", "add", "update", "insert", "appendleft"}
)

type Loop = ast.For | ast.AsyncFor


class SinglePassLoop(NamedTuple):
    path: str
    line_number: int
    reason: str


def is_wildcard(case: ast.match_case) -> bool:
    pattern = case.pattern

    return isinstance(pattern, ast.MatchAs) and pattern.pattern is None


def handlers_exit(statement: ast.Try) -> bool:
    return all(always_exits(handler.body) for handler in statement.handlers)


def try_always_exits(statement: ast.Try) -> bool:
    if always_exits(statement.finalbody):
        return True

    completed = statement.orelse or statement.body

    return always_exits(completed) and handlers_exit(statement)


def match_always_exits(statement: ast.Match) -> bool:
    cases_exit = all(always_exits(case.body) for case in statement.cases)

    return cases_exit and any(is_wildcard(case) for case in statement.cases)


def compound_always_exits(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.If):
        return always_exits(statement.body) and always_exits(statement.orelse)

    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return always_exits(statement.body)

    if isinstance(statement, ast.Try):
        return try_always_exits(statement)

    if isinstance(statement, ast.Match):
        return match_always_exits(statement)

    return False


def always_exits(statements: list[ast.stmt]) -> bool:
    if not statements:
        return False

    last = statements[-1]

    return isinstance(last, EXITS) or compound_always_exits(last)


def continues_in(node: ast.AST) -> bool:
    if isinstance(node, ast.Continue):
        return True

    if isinstance(node, (*LOOPS, *SCOPES)):
        return False

    return any(continues_in(child) for child in ast.iter_child_nodes(node))


def runs_once(loop: Loop) -> bool:
    if not always_exits(loop.body):
        return False

    return not any(continues_in(statement) for statement in loop.body)


def names_in(node: ast.AST) -> set[str]:
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def bound_in(statements: list[ast.stmt]) -> set[str]:
    bound: set[str] = set()

    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)

    return bound


def leaves(node: ast.AST) -> bool:
    for item in ast.walk(node):
        if isinstance(item, (*EXITS, ast.Continue, ast.Yield, ast.YieldFrom)):
            return True

    return False


def filtering_if(statement: ast.stmt, item_names: set[str]) -> bool:
    if not isinstance(statement, ast.If) or statement.orelse:
        return False

    tests_item = bool(names_in(statement.test) & item_names)

    return tests_item and not any(map(leaves, statement.body))


def self_updated(statement: ast.stmt, item_names: set[str]) -> str | None:
    if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
        return None

    target = statement.targets[0]

    if not isinstance(target, ast.Name) or target.id in item_names:
        return None

    return target.id if target.id in names_in(statement.value) else None


def collected_into(statement: ast.stmt, local_names: set[str]) -> str | None:
    call = statement.value if isinstance(statement, ast.Expr) else None

    if not isinstance(call, ast.Call):
        return None

    function = call.func

    if not isinstance(function, ast.Attribute):
        return None

    receiver = function.value
    is_outer = isinstance(receiver, ast.Name) and (
        receiver.id not in local_names
    )

    if function.attr in COLLECTING_METHODS and is_outer:
        return ast.unparse(receiver)

    return None


def accumulated(
    statement: ast.stmt, item_names: set[str], local_names: set[str]
) -> str | None:
    if isinstance(statement, ast.AugAssign):
        return ast.unparse(statement.target)

    total = self_updated(statement, item_names)

    return total or collected_into(statement, local_names)


def returns_none(statement: ast.stmt | None) -> bool:
    if not isinstance(statement, ast.Return):
        return False

    value = statement.value

    return value is None or (
        isinstance(value, ast.Constant) and value.value is None
    )


def callee_name(call: ast.Call) -> str:
    function = call.func

    if isinstance(function, ast.Attribute):
        return function.attr

    return function.id if isinstance(function, ast.Name) else ""


def optional_functions(tree: ast.Module) -> set[str]:
    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        if node.returns is not None and mentions_none(node.returns):
            names.add(node.name)

    return names


def mentions_none(annotation: ast.expr) -> bool:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Constant) and node.value is None:
            return True

        if isinstance(node, ast.Name) and node.id == OPTIONAL:
            return True

    return False


def unchecked_search(
    loop: Loop, following: ast.stmt | None, optional: set[str]
) -> bool:
    last = loop.body[-1]

    if not isinstance(last, ast.Return):
        return False

    if not isinstance(last.value, ast.Call):
        return False

    uses_item = bool(names_in(last.value) & names_in(loop.target))
    may_fail = callee_name(last.value) in optional

    return uses_item and may_fail and returns_none(following)


def returned_names(loop: Loop) -> set[str]:
    last = loop.body[-1]

    if isinstance(last, ast.Return) and last.value is not None:
        return names_in(last.value)

    return set()


def single_pass_reason(
    loop: Loop, following: ast.stmt | None, optional: set[str]
) -> str | None:
    if not runs_once(loop):
        return None

    item_names = names_in(loop.target)
    local_names = bound_in(loop.body) | item_names
    earlier = loop.body[:-1]

    if earlier and filtering_if(earlier[-1], item_names):
        line = earlier[-1].lineno
        return f"the exit after the if on line {line} runs for every item"

    for statement in earlier:
        total = accumulated(statement, item_names, local_names)

        if total is not None and total in returned_names(loop):
            return f"{total} is built up as if every item were visited"

    if unchecked_search(loop, following, optional):
        return "the first item's result is returned even when it is None"

    return None


def statement_blocks(tree: ast.Module) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = [tree.body]

    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block: object = getattr(node, field, None)

            if isinstance(block, list) and node is not tree:
                blocks.append(cast("list[ast.stmt]", block))

    return blocks


class SinglePassLoops:
    def find_in(self, paths: list[str]) -> list[SinglePassLoop]:
        found: set[SinglePassLoop] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            optional = optional_functions(tree)

            for block in statement_blocks(tree):
                found.update(self._in_block(path, block, optional))

        return sorted(found)

    def _in_block(
        self, path: str, block: list[ast.stmt], optional: set[str]
    ) -> list[SinglePassLoop]:
        found: list[SinglePassLoop] = []

        for position, statement in enumerate(block):
            if not isinstance(statement, ast.For | ast.AsyncFor):
                continue

            rest = block[position + 1 :]
            following = rest[0] if rest else None
            reason = single_pass_reason(statement, following, optional)

            if reason is not None:
                found.append(SinglePassLoop(path, statement.lineno, reason))

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for loop in SinglePassLoops().find_in(source_paths):
    location = f"{loop.path}:{loop.line_number}"
    problem = "this loop never gets past its first item"
    _ = sys.stdout.write(f"{location}: {problem} - {loop.reason}\n")
