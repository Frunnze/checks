import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

RESIZING_METHODS = frozenset(
    {
        "add", "clear", "difference_update", "discard", "insert",
        "intersection_update", "pop", "popitem", "popleft", "remove",
        "setdefault", "symmetric_difference_update", "update",
    }
)
APPENDING_METHODS = frozenset({"append", "appendleft", "extend", "extendleft"})
DICT_VIEW_METHODS = frozenset({"items", "keys", "values"})
READING_METHODS = frozenset(
    {
        "copy", "count", "difference", "elements", "fromkeys", "get",
        "index", "intersection", "isdisjoint", "issubset", "issuperset",
        "most_common", "move_to_end", "reverse", "rotate", "sort",
        "subtract", "symmetric_difference", "total", "union",
    }
)
CONTAINER_METHODS = (
    RESIZING_METHODS | APPENDING_METHODS | DICT_VIEW_METHODS | READING_METHODS
)
DICT_TYPE_NAMES = frozenset(
    {"dict", "Dict", "defaultdict", "OrderedDict", "Counter"}
)
LOCKED_TYPE_NAMES = DICT_TYPE_NAMES | {"set", "Set", "deque", "Deque"}
DISPLAY_TYPE_NAMES: dict[type[ast.AST], str] = {
    ast.Dict: "dict",
    ast.DictComp: "dict",
    ast.Set: "set",
    ast.SetComp: "set",
    ast.List: "list",
    ast.ListComp: "list",
}
INSTANCE_NAMES = frozenset({"self", "cls"})
COUNTING_WRAPPER = "enumerate"
SCOPE_NODES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
NESTED_SCOPE_NODES = (
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda
)
LOOP_NODES = (ast.For, ast.AsyncFor, ast.While)
ENDING_NODES = (ast.Return, ast.Raise)

type Scope = (
    ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
)
type Block = list[ast.stmt]
type Binding = tuple[str, str]


class IterationMutation(NamedTuple):
    path: str
    line_number: int
    change: str
    collection: str
    copy: str


class Collection(NamedTuple):
    name: str
    type_name: str
    loop_names: frozenset[str]


class ScopeFacts(NamedTuple):
    known_types: dict[str, str]
    custom_objects: frozenset[str]


class Change(NamedTuple):
    line_number: int
    description: str


class BlockContext(NamedTuple):
    loop_ends_after: bool
    inside_inner_loop: bool


def dotted_name(expression: ast.expr | None) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return f"{owner}.{expression.attr}" if owner else ""

    return ""


def annotated_type(annotation: ast.expr | None) -> str:
    if isinstance(annotation, ast.Subscript):
        return annotated_type(annotation.value)

    return dotted_name(annotation).rpartition(".")[2]


def built_type(value: ast.expr | None) -> str:
    if isinstance(value, ast.Call):
        return annotated_type(value.func)

    if value is None:
        return ""

    return DISPLAY_TYPE_NAMES.get(type(value), "")


def scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    pending = list(ast.iter_child_nodes(scope))

    while pending:
        node = pending.pop()
        yield node

        if not isinstance(node, NESTED_SCOPE_NODES):
            pending.extend(ast.iter_child_nodes(node))


def bindings_by(node: ast.AST) -> list[Binding]:
    if isinstance(node, ast.arg):
        return [(node.arg, annotated_type(node.annotation))]

    if isinstance(node, ast.AnnAssign):
        type_name = annotated_type(node.annotation) or built_type(node.value)
        return [(dotted_name(node.target), type_name)]

    if isinstance(node, ast.Assign):
        type_name = built_type(node.value)
        return [(dotted_name(target), type_name) for target in node.targets]

    return []


def known_types_in(scope: Scope) -> dict[str, str]:
    types_by_name: dict[str, set[str]] = {}

    for node in scope_nodes(scope):
        for name, type_name in bindings_by(node):
            types_by_name.setdefault(name, set()).add(type_name)

    known: dict[str, str] = {}

    for name, type_names in types_by_name.items():
        if len(type_names) == 1:
            known[name] = type_names.pop()

    return known


def custom_objects_in(scope: Scope) -> frozenset[str]:
    names: set[str] = set()

    for node in scope_nodes(scope):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr not in CONTAINER_METHODS
        ):
            names.add(dotted_name(node.func.value))

    return frozenset(names | INSTANCE_NAMES)


def loop_names(target: ast.expr) -> frozenset[str]:
    names: set[str] = set()

    for node in ast.walk(target):
        if isinstance(node, ast.Name):
            names.add(node.id)

    return frozenset(names)


def iterated_reference(iterable: ast.expr) -> tuple[str, bool]:
    if (
        isinstance(iterable, ast.Call)
        and dotted_name(iterable.func) == COUNTING_WRAPPER
        and len(iterable.args) == 1
    ):
        return iterated_reference(iterable.args[0])

    if (
        isinstance(iterable, ast.Call)
        and isinstance(iterable.func, ast.Attribute)
        and iterable.func.attr in DICT_VIEW_METHODS
        and not iterable.args
    ):
        return dotted_name(iterable.func.value), True

    return dotted_name(iterable), False


def nested_blocks(statement: ast.stmt) -> list[Block]:
    if isinstance(statement, ast.If):
        return [statement.body, statement.orelse]

    if isinstance(statement, ast.With | ast.AsyncWith):
        return [statement.body]

    if isinstance(statement, ast.Try | ast.TryStar):
        handlers = [handler.body for handler in statement.handlers]
        return [
            statement.body,
            *handlers,
            statement.orelse,
            statement.finalbody,
        ]

    if isinstance(statement, ast.Match):
        return [case.body for case in statement.cases]

    return []


def may_continue(statement: ast.stmt) -> bool:
    return any(isinstance(node, ast.Continue) for node in ast.walk(statement))


class LoopBody:
    def __init__(self, collection: Collection) -> None:
        self._collection: Collection = collection

    def changes_in(self, block: Block, context: BlockContext) -> list[Change]:
        found: list[Change] = []

        for index, statement in enumerate(block):
            ends_after = self._loop_ends_within(block[index + 1:], context)
            statement_context = context._replace(loop_ends_after=ends_after)
            found.extend(self._changes_by(statement, statement_context))

        return found

    def _loop_ends_within(self, block: Block, context: BlockContext) -> bool:
        for statement in block:
            if isinstance(statement, ENDING_NODES):
                return True

            if isinstance(statement, ast.Break):
                return not context.inside_inner_loop

            if may_continue(statement):
                return False

        return context.loop_ends_after

    def _changes_by(
        self, statement: ast.stmt, context: BlockContext
    ) -> list[Change]:
        if isinstance(statement, NESTED_SCOPE_NODES + ENDING_NODES):
            return []

        if isinstance(statement, LOOP_NODES):
            return self._changes_in_inner_loop(statement, context)

        blocks = nested_blocks(statement)

        if blocks:
            found: list[Change] = []

            for block in blocks:
                found.extend(self.changes_in(block, context))

            return found

        if context.loop_ends_after:
            return []

        return self._changes_in_simple(statement)

    def _changes_in_inner_loop(
        self, loop: ast.For | ast.AsyncFor | ast.While, context: BlockContext
    ) -> list[Change]:
        inner_context = BlockContext(
            loop_ends_after=False, inside_inner_loop=True
        )
        found = self.changes_in(loop.body, inner_context)
        found.extend(self.changes_in(loop.orelse, context))

        return found

    def _changes_in_simple(self, statement: ast.stmt) -> list[Change]:
        found: list[Change] = []

        if (
            isinstance(statement, ast.AugAssign)
            and self._is_collection(statement.target)
            and self._is_locked()
        ):
            found.append(Change(statement.lineno, ast.unparse(statement)))

        for node in scope_nodes(statement):
            description = self._change_made_by(node)

            if description and isinstance(node, ast.expr):
                found.append(Change(node.lineno, description))

        return found

    def _change_made_by(self, node: ast.AST) -> str:
        if isinstance(node, ast.Call) and isinstance(
            node.func, ast.Attribute
        ):
            return self._change_made_by_method(node.func)

        if not isinstance(node, ast.Subscript) or not self._is_collection(
            node.value
        ):
            return ""

        if isinstance(node.ctx, ast.Del):
            return f"del {ast.unparse(node)}"

        return ""

    def _change_made_by_method(self, method: ast.Attribute) -> str:
        if not self._is_collection(method.value):
            return ""

        appends_to_locked = (
            method.attr in APPENDING_METHODS and self._is_locked()
        )

        if method.attr in RESIZING_METHODS or appends_to_locked:
            return f"{ast.unparse(method)}()"

        return ""

    def _is_locked(self) -> bool:
        return self._collection.type_name in LOCKED_TYPE_NAMES

    def _is_collection(self, expression: ast.expr) -> bool:
        return dotted_name(expression) == self._collection.name


class IterationMutations:
    def find_in(self, paths: list[str]) -> list[IterationMutation]:
        found: set[IterationMutation] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for scope in ast.walk(tree):
                if isinstance(scope, SCOPE_NODES):
                    found.update(self._find_in_scope(path, scope))

        return sorted(found)

    def _find_in_scope(
        self, path: str, scope: Scope
    ) -> list[IterationMutation]:
        facts = ScopeFacts(known_types_in(scope), custom_objects_in(scope))
        found: list[IterationMutation] = []

        for node in scope_nodes(scope):
            if isinstance(node, ast.For):
                found.extend(self._find_in_loop(path, node, facts))

        return found

    def _find_in_loop(
        self, path: str, loop: ast.For, facts: ScopeFacts
    ) -> list[IterationMutation]:
        name, is_dict_view = iterated_reference(loop.iter)

        if not name or name in facts.custom_objects:
            return []

        known_type = facts.known_types.get(name, "")
        type_name = "dict" if is_dict_view else known_type
        collection = Collection(name, type_name, loop_names(loop.target))
        context = BlockContext(loop_ends_after=False, inside_inner_loop=False)
        copy = f"list({ast.unparse(loop.iter)})"

        return [
            IterationMutation(
                path, change.line_number, change.description, name, copy
            )
            for change in LoopBody(collection).changes_in(loop.body, context)
        ]


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for mutation in IterationMutations().find_in(source_paths):
    location = f"{mutation.path}:{mutation.line_number}"
    problem = (
        f"{mutation.change} changes {mutation.collection} while a for loop"
        " iterates over it, so items are skipped or a RuntimeError is raised"
    )
    fix = f"loop over a copy such as {mutation.copy} or build a new one"
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
