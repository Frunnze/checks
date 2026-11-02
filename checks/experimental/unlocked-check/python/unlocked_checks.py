import ast
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

SELF = "self"
INITIALIZER = "__init__"
LOCK_WORDS = ("lock", "mutex")
ACQUIRE_WORDS = ("acquire", "lock")
RELEASE_WORDS = ("release", "unlock")
GUARDS_ELSEWHERE = "the lock that guards it elsewhere"
TAKEN_HERE = "the lock this method takes"

type MethodNode = ast.FunctionDef | ast.AsyncFunctionDef
type Statements = list[ast.stmt]


class CheckThenSet(NamedTuple):
    statement: ast.If
    attribute: str


class UnlockedCheck(NamedTuple):
    path: str
    line_number: int
    attribute: str
    lock: str


def self_attribute(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Attribute):
        return None

    if not isinstance(node.value, ast.Name) or node.value.id != SELF:
        return None

    return node.attr


def contains_any(name: str, words: tuple[str, ...]) -> bool:
    lowered = name.lower()

    return any(word in lowered for word in words)


def lock_holder(expression: ast.expr) -> ast.expr:
    if not isinstance(expression, ast.Call):
        return expression

    if not isinstance(expression.func, ast.Attribute):
        return expression

    return expression.func.value


def lock_attribute(item: ast.withitem) -> str | None:
    name = self_attribute(lock_holder(item.context_expr))

    if name is None or not contains_any(name, LOCK_WORDS):
        return None

    return name


def locked_blocks(method: MethodNode) -> list[ast.With]:
    blocks: list[ast.With] = []

    for node in ast.walk(method):
        if not isinstance(node, ast.With):
            continue

        if any(lock_attribute(item) is not None for item in node.items):
            blocks.append(node)

    return blocks


def nodes_in(roots: Iterable[ast.AST]) -> set[ast.AST]:
    found: set[ast.AST] = set()

    for root in roots:
        found.update(ast.walk(root))

    return found


def calls_method_named(statement: ast.stmt, words: tuple[str, ...]) -> bool:
    if not isinstance(statement, ast.Expr):
        return False

    call = statement.value

    if not isinstance(call, ast.Call):
        return False

    if not isinstance(call.func, ast.Attribute):
        return False

    return contains_any(call.func.attr, words)


def child_blocks(node: ast.AST) -> list[Statements]:
    if isinstance(node, ast.If | ast.For | ast.AsyncFor | ast.While):
        return [node.body, node.orelse]

    if isinstance(node, ast.Try | ast.TryStar):
        return [node.body, node.orelse, node.finalbody]

    if isinstance(
        node,
        ast.FunctionDef
        | ast.AsyncFunctionDef
        | ast.ClassDef
        | ast.With
        | ast.AsyncWith
        | ast.ExceptHandler
        | ast.match_case,
    ):
        return [node.body]

    return []


def held_statements(block: Statements) -> Statements:
    held: Statements = []
    is_held = False

    for statement in block:
        if calls_method_named(statement, RELEASE_WORDS):
            is_held = False
        elif calls_method_named(statement, ACQUIRE_WORDS):
            is_held = True
        elif is_held:
            held.append(statement)

    return held


def releases_finally(statement: ast.Try | ast.TryStar) -> bool:
    return any(
        calls_method_named(cleanup, RELEASE_WORDS)
        for cleanup in statement.finalbody
    )


def manually_locked_nodes(method: MethodNode) -> set[ast.AST]:
    held: Statements = []

    for node in ast.walk(method):
        if isinstance(node, ast.Try | ast.TryStar) and releases_finally(node):
            held.extend(node.body)

        for block in child_blocks(node):
            held.extend(held_statements(block))

    return nodes_in(held)


def tested_attribute(test: ast.expr) -> str | None:
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return self_attribute(test.operand)

    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None

    operator = test.ops[0]
    right = test.comparators[0]

    if isinstance(operator, ast.NotIn):
        return self_attribute(right)

    is_none = isinstance(right, ast.Constant) and right.value is None

    if isinstance(operator, ast.Is) and is_none:
        return self_attribute(test.left)

    return None


def stored_attributes(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AnnAssign):
        targets = [statement.target]
    else:
        return set()

    stored: set[str] = set()

    for target in targets:
        holder = target.value if isinstance(target, ast.Subscript) else target
        name = self_attribute(holder)

        if name is not None:
            stored.add(name)

    return stored


def check_then_sets(method: MethodNode) -> list[CheckThenSet]:
    found: list[CheckThenSet] = []

    for node in ast.walk(method):
        if not isinstance(node, ast.If):
            continue

        name = tested_attribute(node.test)

        if name is None or contains_any(name, LOCK_WORDS):
            continue

        if any(name in stored_attributes(child) for child in node.body):
            found.append(CheckThenSet(node, name))

    return found


def attributes_in(nodes: Iterable[ast.AST]) -> set[str]:
    found: set[str] = set()

    for node in nodes:
        name = self_attribute(node)

        if name is not None:
            found.add(name)

    return found


def is_checked_method(method: MethodNode) -> bool:
    if isinstance(method, ast.AsyncFunctionDef):
        return False

    return method.name != INITIALIZER


class LockedClass:
    def __init__(self, path: str, methods: list[MethodNode]) -> None:
        self._path: str = path
        self._methods: list[MethodNode] = methods
        every_locked = [
            block for method in methods for block in locked_blocks(method)
        ]
        self._guarded: set[str] = attributes_in(nodes_in(every_locked))
        self.is_locked: bool = bool(every_locked)

    def unlocked_checks(self) -> list[UnlockedCheck]:
        found: list[UnlockedCheck] = []

        for method in self._methods:
            if is_checked_method(method):
                found.extend(self._checks_in(method))

        return found

    def _checks_in(self, method: MethodNode) -> list[UnlockedCheck]:
        checks = check_then_sets(method)

        if not checks:
            return []

        own_locked = locked_blocks(method)
        locked_nodes = nodes_in(own_locked) | manually_locked_nodes(method)
        found: list[UnlockedCheck] = []

        for check in checks:
            if check.statement in locked_nodes:
                continue

            lock = self._lock_of(check, has_own_lock=bool(own_locked))

            if lock is not None:
                found.append(
                    UnlockedCheck(
                        self._path,
                        check.statement.lineno,
                        check.attribute,
                        lock,
                    )
                )

        return found

    def _lock_of(
        self, check: CheckThenSet, *, has_own_lock: bool
    ) -> str | None:
        if check.attribute in self._guarded:
            return GUARDS_ELSEWHERE

        if has_own_lock:
            return TAKEN_HERE

        return None


def class_methods(class_node: ast.ClassDef) -> list[MethodNode]:
    methods: list[MethodNode] = []

    for statement in class_node.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            methods.append(statement)

    return methods


class UnlockedChecks:
    def find_in(self, paths: list[str]) -> list[UnlockedCheck]:
        found: set[UnlockedCheck] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue

                locked_class = LockedClass(path, class_methods(node))

                if locked_class.is_locked:
                    found.update(locked_class.unlocked_checks())

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for unlocked in UnlockedChecks().find_in(source_paths):
    location = f"{unlocked.path}:{unlocked.line_number}"
    problem = (
        f"self.{unlocked.attribute} is checked then set outside"
        f" {unlocked.lock}, so two threads can both pass the check"
    )
    fix = "do the check and the set under the lock"
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
