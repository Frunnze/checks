import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

TEXT_KEEPING_METHODS = frozenset(
    {
        "capitalize", "casefold", "center", "expandtabs", "format", "join",
        "ljust", "lower", "lstrip", "removeprefix", "removesuffix",
        "replace", "rjust", "rstrip", "strip", "swapcase", "title",
        "translate", "upper", "zfill",
    }
)
TEXT_SPLITTING_METHODS = {
    "split": "list",
    "rsplit": "list",
    "splitlines": "list",
    "partition": "tuple",
    "rpartition": "tuple",
}
PATH_KEEPING_METHODS = frozenset(
    {
        "absolute", "expanduser", "joinpath", "relative_to", "resolve",
        "with_name", "with_stem", "with_suffix",
    }
)
SET_METHODS = frozenset(
    {"difference", "intersection", "symmetric_difference", "union"}
)
RESULT_FAMILIES: dict[str, dict[str, str]] = {
    "str": {
        **dict.fromkeys(TEXT_KEEPING_METHODS, "str"),
        **TEXT_SPLITTING_METHODS,
        "encode": "bytes",
    },
    "bytes": {
        **dict.fromkeys(TEXT_KEEPING_METHODS, "bytes"),
        **TEXT_SPLITTING_METHODS,
        "decode": "str",
    },
    "datetime": {
        "astimezone": "datetime",
        "isoformat": "str",
        "replace": "datetime",
    },
    "date": {"isoformat": "str", "replace": "date"},
    "time": {"isoformat": "str", "replace": "time"},
    "Path": dict.fromkeys(PATH_KEEPING_METHODS, "Path"),
    "tuple": {"count": "int"},
    "frozenset": dict.fromkeys(SET_METHODS, "frozenset"),
}
PATH_CLASSES = (
    "Path", "PurePath", "PosixPath", "PurePosixPath", "WindowsPath",
    "PureWindowsPath",
)
CONSTRUCTED_FAMILIES = {
    **dict.fromkeys(PATH_CLASSES, "Path"),
    "str": "str",
    "repr": "str",
    "bytes": "bytes",
    "datetime": "datetime",
    "date": "date",
    "tuple": "tuple",
    "frozenset": "frozenset",
}
ANNOTATED_FAMILIES = {
    **CONSTRUCTED_FAMILIES,
    "LiteralString": "str",
    "time": "time",
    "Tuple": "tuple",
    "FrozenSet": "frozenset",
}
CONSTRUCTOR_MODULES = frozenset({"builtins", "datetime", "pathlib"})
FACTORY_METHODS = {
    "datetime": frozenset(
        {
            "combine", "fromisoformat", "fromtimestamp", "now", "strptime",
            "today", "utcfromtimestamp", "utcnow",
        }
    ),
    "date": frozenset({"fromisoformat", "fromtimestamp", "today"}),
    "Path": frozenset({"cwd", "home"}),
}
CONSTANT_FAMILIES: dict[type, str] = {str: "str", bytes: "bytes"}
WRAPPING_ANNOTATIONS = frozenset({"ClassVar", "Final", "Optional"})
JOINING_OPERATIONS: dict[type[ast.operator], frozenset[str]] = {
    ast.Add: frozenset({"str", "bytes", "tuple"}),
    ast.Mod: frozenset({"str", "bytes"}),
    ast.Div: frozenset({"Path"}),
}
PURE_BUILTINS = frozenset({"abs", "reversed", "round", "sorted"})
CHECKING_METHODS = frozenset({"decode", "encode", "relative_to"})
CHECKING_KEYWORD = "strict"
ERROR_CONTEXTS = frozenset(
    {
        "assertRaises", "assertRaisesRegex", "assertRaisesRegexp", "raises",
        "suppress",
    }
)
DISCARD_NAME = "_"
TEST_FOLDERS = frozenset({"test", "tests", "_tests", "benchmarks"})
TEST_PREFIX = "test_"
TEST_SUFFIX = "_test.py"
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
NESTED_SCOPE_NODES = (*DEFINITION_NODES, ast.Lambda)

type Value = ast.expr | None
type Chain = list[ScopeBindings]


class DiscardedResult(NamedTuple):
    path: str
    line_number: int
    call: str
    reason: str


def dotted_name(expression: ast.expr | None) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return f"{owner}.{expression.attr}" if owner else ""

    return ""


def last_name(expression: ast.expr | None) -> str:
    return dotted_name(expression).rpartition(".")[2]


def only(families: set[str]) -> str:
    return next(iter(families)) if len(families) == 1 else ""


def is_none(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is None


def annotated_family(annotation: ast.expr | None) -> str:
    if isinstance(annotation, ast.BinOp) and is_none(annotation.right):
        return annotated_family(annotation.left)

    if isinstance(annotation, ast.BinOp) and is_none(annotation.left):
        return annotated_family(annotation.right)

    if not isinstance(annotation, ast.Subscript):
        return ANNOTATED_FAMILIES.get(last_name(annotation), "")

    if last_name(annotation.value) in WRAPPING_ANNOTATIONS:
        return annotated_family(annotation.slice)

    return annotated_family(annotation.value)


def scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    pending = list(ast.iter_child_nodes(scope))

    while pending:
        node = pending.pop()
        yield node

        if not isinstance(node, NESTED_SCOPE_NODES):
            pending.extend(ast.iter_child_nodes(node))


class ScopeBindings:
    def __init__(self) -> None:
        self._declared: dict[str, set[str]] = {}
        self._assigned: dict[str, list[Value]] = {}

    def declare(self, name: str, family: str) -> None:
        self._declared.setdefault(name, set()).add(family)

    def assign(self, name: str, value: Value) -> None:
        self._assigned.setdefault(name, []).append(value)

    def binds(self, name: str) -> bool:
        return name in self._declared or name in self._assigned

    def declared_family(self, name: str) -> str | None:
        if name not in self._declared:
            return None

        return only(self._declared[name])

    def values_of(self, name: str) -> list[Value]:
        return self._assigned.get(name, [])


class BindingCollector:
    def __init__(self) -> None:
        self._bindings: ScopeBindings = ScopeBindings()
        self._typed_targets: set[int] = set()

    def collect(self, scope: ast.AST) -> ScopeBindings:
        for node in scope_nodes(scope):
            self._collect_from(node)

        return self._bindings

    def _collect_from(self, node: ast.AST) -> None:
        if isinstance(node, ast.arg):
            self._bind(node.arg, annotated_family(node.annotation), None)
        elif isinstance(node, ast.AnnAssign):
            self._bind_target(node.target, node.annotation, node.value)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            self._bind_target(node.targets[0], None, node.value)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name.partition(".")[0]
                self._bindings.assign(name, None)
        elif isinstance(node, DEFINITION_NODES):
            self._bindings.assign(node.name, None)
        elif isinstance(node, ast.Name | ast.Attribute):
            self._bind_stored(node)

    def _bind_target(
        self, target: ast.expr, annotation: Value, value: Value
    ) -> None:
        name = dotted_name(target)

        if name:
            self._typed_targets.add(id(target))
            self._bind(name, annotated_family(annotation), value)

    def _bind(self, name: str, family: str, value: Value) -> None:
        if family:
            self._bindings.declare(name, family)
        else:
            self._bindings.assign(name, value)

    def _bind_stored(self, node: ast.Name | ast.Attribute) -> None:
        stored = isinstance(node.ctx, ast.Store | ast.Del)

        if stored and id(node) not in self._typed_targets:
            self._bindings.assign(dotted_name(node), None)


def bindings_of(scope: ast.AST) -> ScopeBindings:
    return BindingCollector().collect(scope)


def attribute_declarations_of(class_node: ast.ClassDef) -> ScopeBindings:
    declarations = ScopeBindings()

    for node in ast.walk(class_node):
        if not isinstance(node, ast.AnnAssign):
            continue

        family = annotated_family(node.annotation)
        name = dotted_name(node.target)
        is_field = node in class_node.body and isinstance(
            node.target, ast.Name
        )

        if is_field:
            name = f"self.{name}"

        if family and name.startswith("self."):
            declarations.declare(name, family)

    return declarations


class Families:
    def __init__(self, chain: Chain) -> None:
        self._chain: Chain = chain
        self._resolving: set[str] = set()

    def of(self, expression: ast.expr) -> str:
        if isinstance(expression, ast.Constant):
            return CONSTANT_FAMILIES.get(type(expression.value), "")

        if isinstance(expression, ast.JoinedStr):
            return "str"

        if isinstance(expression, ast.Tuple):
            return "tuple"

        if isinstance(expression, ast.Call):
            return self._of_call(expression)

        if isinstance(expression, ast.BinOp):
            return self._of_operation(expression)

        name = dotted_name(expression)
        return self._of_name(name) if name else ""

    def _of_name(self, name: str) -> str:
        for bindings in self._chain:
            if bindings.binds(name):
                return self._of_bound(bindings, name)

        return ""

    def _of_bound(self, bindings: ScopeBindings, name: str) -> str:
        declared = bindings.declared_family(name)

        if declared is not None:
            return declared

        if name in self._resolving:
            return ""

        self._resolving.add(name)
        families = {
            self.of(value) if value else ""
            for value in bindings.values_of(name)
        }
        self._resolving.discard(name)

        return only(families)

    def _of_call(self, call: ast.Call) -> str:
        callee = call.func

        if isinstance(callee, ast.Name):
            return CONSTRUCTED_FAMILIES.get(callee.id, "")

        if not isinstance(callee, ast.Attribute):
            return ""

        owner_family = self.of(callee.value)

        if owner_family:
            return RESULT_FAMILIES.get(owner_family, {}).get(callee.attr, "")

        return self._of_class_call(callee)

    def _of_class_call(self, callee: ast.Attribute) -> str:
        owner = last_name(callee.value)

        if callee.attr in FACTORY_METHODS.get(owner, frozenset()):
            return owner

        if owner in CONSTRUCTOR_MODULES:
            return CONSTRUCTED_FAMILIES.get(callee.attr, "")

        return ""

    def _of_operation(self, operation: ast.BinOp) -> str:
        families = JOINING_OPERATIONS.get(type(operation.op), frozenset())
        left = self.of(operation.left)

        if left not in families:
            return ""

        if isinstance(operation.op, ast.Add):
            return left if self.of(operation.right) == left else ""

        return left


def discarded_call(statement: ast.AST) -> ast.Call | None:
    if isinstance(statement, ast.Expr) and isinstance(
        statement.value, ast.Call
    ):
        return statement.value

    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and dotted_name(statement.targets[0]) == DISCARD_NAME
        and isinstance(statement.value, ast.Call)
    ):
        return statement.value

    return None


def guards_errors(node: ast.AST) -> bool:
    if isinstance(node, ast.Try | ast.TryStar):
        return bool(node.handlers)

    if not isinstance(node, ast.With | ast.AsyncWith):
        return False

    return any(
        isinstance(item.context_expr, ast.Call)
        and last_name(item.context_expr.func) in ERROR_CONTEXTS
        for item in node.items
    )


def statements_kept_for_errors(scope: ast.AST) -> set[int]:
    kept: set[int] = set()

    for node in scope_nodes(scope):
        if guards_errors(node) and isinstance(
            node, ast.Try | ast.TryStar | ast.With | ast.AsyncWith
        ):
            kept.update(statements_within(node.body))

    return kept


def statements_within(block: list[ast.stmt]) -> set[int]:
    within: set[int] = set()

    for statement in block:
        within.add(id(statement))
        within.update(id(node) for node in scope_nodes(statement))

    return within


def checks_for_errors(call: ast.Call) -> bool:
    if any(keyword.arg == CHECKING_KEYWORD for keyword in call.keywords):
        return True

    callee = call.func

    return (
        isinstance(callee, ast.Attribute) and callee.attr in CHECKING_METHODS
    )


class FileDiscards:
    def __init__(self, path: str) -> None:
        self._path: str = path

    def find_in(self, tree: ast.Module) -> list[DiscardedResult]:
        return self._find_in_scope(tree, [bindings_of(tree)])

    def _find_in_scope(
        self, scope: ast.AST, chain: Chain
    ) -> list[DiscardedResult]:
        families = Families(chain)
        kept = statements_kept_for_errors(scope)
        found: list[DiscardedResult] = []

        for node in scope_nodes(scope):
            if isinstance(node, FUNCTION_NODES):
                inner_chain = [bindings_of(node), *chain]
                found.extend(self._find_in_scope(node, inner_chain))
            elif isinstance(node, ast.ClassDef):
                class_chain = [attribute_declarations_of(node), *chain]
                found.extend(self._find_in_scope(node, class_chain))
            elif id(node) not in kept:
                found.extend(self._discard_by(node, families, chain))

        return found

    def _discard_by(
        self, statement: ast.AST, families: Families, chain: Chain
    ) -> list[DiscardedResult]:
        call = discarded_call(statement)

        if call is None or checks_for_errors(call):
            return []

        reason = self._reason(call, families, chain)

        if not reason:
            return []

        callee = ast.unparse(call.func)
        return [
            DiscardedResult(self._path, call.lineno, f"{callee}()", reason)
        ]

    def _reason(self, call: ast.Call, families: Families, chain: Chain) -> str:
        callee = call.func

        if isinstance(callee, ast.Attribute):
            family = families.of(callee.value)
            pure = callee.attr in RESULT_FAMILIES.get(family, {})
            return f"{family} values never change in place" if pure else ""

        name = dotted_name(callee)
        shadowed = any(bindings.binds(name) for bindings in chain)

        if name in PURE_BUILTINS and not shadowed:
            return f"{name}() changes nothing in place"

        return ""


def is_test_file(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1]
    in_test_folder = any(part in TEST_FOLDERS for part in parts[:-1])

    return in_test_folder or name.startswith(TEST_PREFIX) or (
        name.endswith(TEST_SUFFIX)
    )


class DiscardedResults:
    def find_in(self, paths: list[str]) -> list[DiscardedResult]:
        found: set[DiscardedResult] = set()

        for path in paths:
            if is_test_file(path):
                continue

            tree = ast.parse(Path(path).read_bytes(), path)
            found.update(FileDiscards(path).find_in(tree))

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for discarded in DiscardedResults().find_in(source_paths):
    location = f"{discarded.path}:{discarded.line_number}"
    problem = f"the result of {discarded.call} is thrown away"
    fix = f"{discarded.reason}, so assign the result or drop the call"
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
