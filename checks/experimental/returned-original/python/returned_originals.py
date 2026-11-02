import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

COPY_CALLS = frozenset(
    {"list", "dict", "set", "deepcopy", "copy", "bytearray", "OrderedDict"}
)
COPY_METHOD = "copy"
MUTATORS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "update",
        "setdefault",
        "sort",
        "reverse",
        "clear",
        "add",
        "discard",
        "popitem",
        "appendleft",
        "extendleft",
    }
)
READERS = frozenset(
    {
        "enumerate",
        "len",
        "zip",
        "iter",
        "reversed",
        "range",
        "any",
        "all",
        "sum",
        "min",
        "max",
    }
)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
ITERATIONS = (ast.For, ast.comprehension)
CHANGES = (ast.Store, ast.Del)
MEMBERSHIP = (ast.In, ast.NotIn)

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type Parents = dict[ast.AST, ast.AST]


class Assignment(NamedTuple):
    statement: ast.stmt
    name: str
    value: ast.expr


class Copy(NamedTuple):
    line_number: int
    name: str
    source: str


class ReturnedOriginal(NamedTuple):
    path: str
    line_number: int
    source: str
    copy: str
    copy_line_number: int


def called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id

    if isinstance(call.func, ast.Attribute):
        return call.func.attr

    return None


def copied_call_name(call: ast.Call) -> str | None:
    function = call.func
    has_one_argument = len(call.args) == 1 and not call.keywords

    if has_one_argument and called_name(call) in COPY_CALLS:
        argument = call.args[0]
        return argument.id if isinstance(argument, ast.Name) else None

    if isinstance(function, ast.Attribute) and not call.args:
        is_copy_method = function.attr == COPY_METHOD
        copied = function.value

        if is_copy_method and isinstance(copied, ast.Name):
            return copied.id

    return None


def sliced_name(subscript: ast.Subscript) -> str | None:
    bounds = subscript.slice
    sliced = subscript.value

    if not isinstance(bounds, ast.Slice) or not isinstance(sliced, ast.Name):
        return None

    if bounds.lower is not None or bounds.upper is not None:
        return None

    return sliced.id


def copied_name(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Call):
        return copied_call_name(expression)

    if isinstance(expression, ast.Subscript):
        return sliced_name(expression)

    return None


def assigned(node: ast.AST) -> Assignment | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]

        if isinstance(target, ast.Name):
            return Assignment(node, target.id, node.value)

    if isinstance(node, ast.AnnAssign) and node.value is not None:
        target = node.target

        if isinstance(target, ast.Name):
            return Assignment(node, target.id, node.value)

    return None


def own_nodes(function: FunctionNode) -> Iterator[ast.AST]:
    pending: list[ast.AST] = list(function.body)

    while pending:
        node = pending.pop()
        yield node

        if not isinstance(node, SCOPES):
            pending.extend(ast.iter_child_nodes(node))


def copies_in(function: FunctionNode) -> Iterator[Copy]:
    for node in own_nodes(function):
        assignment = assigned(node)

        if assignment is None:
            continue

        source = copied_name(assignment.value)
        line_number = assignment.statement.lineno

        if source is not None:
            yield Copy(line_number, assignment.name, source)


def returned_names(function: FunctionNode) -> dict[str, list[int]]:
    returned: dict[str, list[int]] = {}

    for node in own_nodes(function):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
            returned.setdefault(node.value.id, []).append(node.lineno)

    return returned


def read_names(function: FunctionNode) -> dict[str, list[ast.Name]]:
    reads: dict[str, list[ast.Name]] = {}

    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            reads.setdefault(node.id, []).append(node)

    return reads


def last_store_lines(function: FunctionNode) -> dict[str, int]:
    last_stores: dict[str, int] = {}

    for node in ast.walk(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            earlier = last_stores.get(node.id, node.lineno)
            last_stores[node.id] = max(earlier, node.lineno)

    return last_stores


class FunctionFacts:
    def __init__(self, function: FunctionNode) -> None:
        self.reads: dict[str, list[ast.Name]] = read_names(function)
        self.returned: dict[str, list[int]] = returned_names(function)
        self.last_stores: dict[str, int] = last_store_lines(function)


def parents_in(tree: ast.Module) -> Parents:
    parents: Parents = {}

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    return parents


def changes(read: ast.Name, parents: Parents) -> bool:
    parent = parents.get(read)

    if isinstance(parent, ast.Subscript) and parent.value is read:
        return isinstance(parent.ctx, CHANGES)

    if isinstance(parent, ast.Attribute) and parent.value is read:
        is_mutator = parent.attr in MUTATORS
        return is_mutator and isinstance(parents.get(parent), ast.Call)

    return False


def is_reading_call(read: ast.Name, call: ast.Call) -> bool:
    is_argument = any(argument is read for argument in call.args)
    reader = call.func

    return (
        is_argument
        and isinstance(reader, ast.Name)
        and reader.id in READERS
    )


def is_looked_up(read: ast.Name, comparison: ast.Compare) -> bool:
    pairs = zip(comparison.ops, comparison.comparators, strict=True)

    return any(
        isinstance(operator, MEMBERSHIP) and operand is read
        for operator, operand in pairs
    )


def only_reads(read: ast.Name, parents: Parents) -> bool:
    parent = parents.get(read)

    if isinstance(parent, ast.Subscript):
        return parent.value is read

    if isinstance(parent, ast.Call):
        return is_reading_call(read, parent)

    if isinstance(parent, ITERATIONS):
        return parent.iter is read

    if isinstance(parent, ast.Compare):
        return not is_looked_up(read, parent)

    return False


def is_changed_in_place(reads: list[ast.Name], parents: Parents) -> bool:
    changed = False

    for read in reads:
        if changes(read, parents):
            changed = True
        elif not only_reads(read, parents):
            return False

    return changed


class ReturnedOriginals:
    def __init__(self, path: str, parents: Parents) -> None:
        self._path: str = path
        self._parents: Parents = parents
        self.found: list[ReturnedOriginal] = []

    def check(self, function: FunctionNode) -> None:
        copies = list(copies_in(function))

        if not copies:
            return

        facts = FunctionFacts(function)

        for copy in copies:
            if not self._is_dropped(copy, facts):
                continue

            for line_number in facts.returned.get(copy.source, []):
                if line_number > copy.line_number:
                    self._add(line_number, copy)

    def _is_dropped(self, copy: Copy, facts: FunctionFacts) -> bool:
        copy_reads = facts.reads.get(copy.name, [])
        source_reads = facts.reads.get(copy.source, [])
        last_store = facts.last_stores.get(copy.source, copy.line_number)

        if last_store > copy.line_number:
            return False

        if any(changes(read, self._parents) for read in source_reads):
            return False

        return is_changed_in_place(copy_reads, self._parents)

    def _add(self, line_number: int, copy: Copy) -> None:
        self.found.append(
            ReturnedOriginal(
                self._path,
                line_number,
                copy.source,
                copy.name,
                copy.line_number,
            )
        )


class ReturnedOriginalFinder:
    def find_in(self, paths: list[str]) -> list[ReturnedOriginal]:
        found: set[ReturnedOriginal] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            originals = ReturnedOriginals(path, parents_in(tree))

            for node in ast.walk(tree):
                if isinstance(node, FUNCTIONS):
                    originals.check(node)

            found.update(originals.found)

        return sorted(found)


def describe(original: ReturnedOriginal) -> str:
    location = f"{original.path}:{original.line_number}"
    copy = f"its copy {original.copy} (line {original.copy_line_number})"
    problem = f"returns {original.source} unchanged, but {copy} was changed"
    return f"{location}: {problem} - return {original.copy} instead"


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for returned_original in ReturnedOriginalFinder().find_in(source_paths):
    _ = sys.stdout.write(f"{describe(returned_original)}\n")
