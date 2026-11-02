import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

VALUE_KINDS: dict[type, str] = {
    str: "str",
    bytes: "bytes",
    int: "int",
    float: "float",
    complex: "complex",
}
SINGLETON_NAMES = frozenset(
    {"None", "True", "False", "Ellipsis", "NotImplemented"}
)
FRESH_BUILTINS = frozenset(
    {"bytes", "float", "format", "int", "len", "repr", "str"}
)
FRESH_METHODS = frozenset(
    {
        "capitalize", "casefold", "center", "decode", "encode", "expandtabs",
        "format", "hexdigest", "isoformat", "join", "ljust", "lower",
        "lstrip", "removeprefix", "removesuffix", "replace", "rjust",
        "rstrip", "strftime", "strip", "swapcase", "title", "translate",
        "upper", "zfill",
    }
)
SIGN_OPERATORS = (ast.USub, ast.UAdd, ast.Invert)
FLOAT_KIND = "float"
EQUALITY_FOR: dict[type[ast.cmpop], str] = {ast.Is: "==", ast.IsNot: "!="}
INSTANCE_NAMES = frozenset({"self", "cls"})
SENTINEL_LOOKUPS = frozenset({"get", "getattr", "next", "pop"})
LOOKUP_WITH_DEFAULT = 2
PLAIN_BASE = "object"
PACKAGE_MODULE = "__init__"
DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
NESTED_SCOPE_NODES = (*DEFINITION_NODES, ast.Lambda)
LOCAL_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

type Binding = tuple[str, str]
type LocalScope = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda


class IdentityComparison(NamedTuple):
    path: str
    line_number: int
    comparison: str
    reason: str
    replacement: str


class ScopeContext(NamedTuple):
    local_names: frozenset[str]
    module_names: frozenset[str]
    class_name: str
    sentinels: dict[str, str]
    value_subjects: frozenset[str]


VALUE_OPERATORS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)


def value_subjects_in(scope: ast.AST) -> frozenset[str]:
    subjects: set[str] = set()

    for node in ast.walk(scope):
        if not isinstance(node, ast.Compare):
            continue

        left = node.left

        for operator, right in zip(node.ops, node.comparators, strict=True):
            if isinstance(operator, VALUE_OPERATORS):
                subjects.update((ast.dump(left), ast.dump(right)))

            left = right

    return frozenset(subjects)


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return f"{owner}.{expression.attr}" if owner else ""

    return ""


def called_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr

    return dotted_name(call.func)


def literal_kind(expression: ast.expr) -> str:
    if isinstance(expression, ast.Constant):
        if isinstance(expression.value, bool):
            return ""

        return VALUE_KINDS.get(type(expression.value), "")

    if isinstance(expression, ast.UnaryOp) and isinstance(
        expression.op, SIGN_OPERATORS
    ):
        return literal_kind(expression.operand)

    if isinstance(expression, ast.BinOp):
        return arithmetic_kind(expression)

    if isinstance(expression, ast.Tuple):
        literal = all(literal_kind(element) for element in expression.elts)
        return "tuple" if literal else ""

    return ""


def arithmetic_kind(operation: ast.BinOp) -> str:
    left = literal_kind(operation.left)

    if not left or not literal_kind(operation.right):
        return ""

    return FLOAT_KIND if isinstance(operation.op, ast.Div) else left


def kind_of(kinds: set[str]) -> str:
    if not kinds or "" in kinds:
        return ""

    return " or ".join(sorted(kinds))


def scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    pending = list(ast.iter_child_nodes(scope))

    while pending:
        node = pending.pop()
        yield node

        if not isinstance(node, NESTED_SCOPE_NODES):
            pending.extend(ast.iter_child_nodes(node))


def valued_target(node: ast.AST) -> tuple[ast.Name, ast.expr] | None:
    target: ast.expr

    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value = node.targets[0], node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        target, value = node.target, node.value
    else:
        return None

    return (target, value) if isinstance(target, ast.Name) else None


def names_bound_by(node: ast.AST) -> list[str]:
    if isinstance(node, ast.arg):
        return [node.arg]

    if isinstance(node, ast.Name) and isinstance(
        node.ctx, ast.Store | ast.Del
    ):
        return [node.id]

    if isinstance(node, DEFINITION_NODES):
        return [node.name]

    if isinstance(node, ast.ExceptHandler) and node.name:
        return [node.name]

    if isinstance(node, ast.Import | ast.ImportFrom):
        return [
            alias.asname or alias.name.partition(".")[0]
            for alias in node.names
        ]

    return []


def bound_names(scope: ast.AST) -> frozenset[str]:
    names: set[str] = set()
    declared_global: set[str] = set()

    for node in scope_nodes(scope):
        names.update(names_bound_by(node))

        if isinstance(node, ast.Global):
            declared_global.update(node.names)

    return frozenset(names - declared_global)


def default_sentinels(function: LocalScope) -> dict[str, str]:
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaulted = positional[len(positional) - len(arguments.defaults):]
    sentinels: dict[str, str] = {}

    for argument, default in zip(defaulted, arguments.defaults, strict=True):
        sentinels[argument.arg] = dotted_name(default)

    for argument, keyword_default in zip(
        arguments.kwonlyargs, arguments.kw_defaults, strict=True
    ):
        if keyword_default is not None:
            sentinels[argument.arg] = dotted_name(keyword_default)

    return sentinels


def lookup_sentinel(node: ast.AST) -> dict[str, str]:
    valued = valued_target(node)

    if valued is None:
        return {}

    target, value = valued

    if not isinstance(value, ast.Call):
        return {}

    if len(value.args) < LOOKUP_WITH_DEFAULT:
        return {}

    if called_name(value) not in SENTINEL_LOOKUPS:
        return {}

    return {target.id: dotted_name(value.args[-1])}


def sentinels_of(function: LocalScope) -> dict[str, str]:
    sentinels = default_sentinels(function)

    for node in scope_nodes(function):
        sentinels.update(lookup_sentinel(node))

    return {name: marker for name, marker in sentinels.items() if marker}


def is_sentinel_check(
    left: ast.expr, right: ast.expr, sentinels: dict[str, str]
) -> bool:
    for name, marker in ((left, right), (right, left)):
        if isinstance(name, ast.Name) and dotted_name(marker) == sentinels.get(
            name.id
        ):
            return True

    return False


def is_plain_class(class_node: ast.ClassDef) -> bool:
    plain_bases = all(
        dotted_name(base) == PLAIN_BASE for base in class_node.bases
    )

    return (
        plain_bases
        and not class_node.keywords
        and not class_node.decorator_list
    )


def module_name_of(path: str) -> str:
    source = Path(path)

    if source.stem == PACKAGE_MODULE:
        return source.parent.name

    return source.stem


class BindingCollector:
    def __init__(self) -> None:
        self._found: list[Binding] = []
        self._valued_targets: set[int] = set()

    def collect(self, scope: ast.AST) -> list[Binding]:
        for node in scope_nodes(scope):
            self._collect_from(node)

        return self._found

    def _collect_from(self, node: ast.AST) -> None:
        valued = valued_target(node)

        if valued is not None:
            target, value = valued
            self._valued_targets.add(id(target))
            self._found.append((target.id, literal_kind(value)))
        elif isinstance(node, DEFINITION_NODES):
            self._found.append((node.name, ""))
        elif isinstance(node, ast.Name) and isinstance(
            node.ctx, ast.Store | ast.Del
        ):
            self._collect_stored(node)

    def _collect_stored(self, node: ast.Name) -> None:
        if id(node) not in self._valued_targets:
            self._found.append((node.id, ""))


class ProjectConstants:
    def __init__(self) -> None:
        self._module_kinds: dict[str, set[str]] = {}
        self._class_kinds: dict[str, set[str]] = {}
        self._attribute_targets: set[str] = set()
        self._modules: set[str] = set()
        self._classes: set[str] = set()

    def learn(self, path: str, tree: ast.Module) -> None:
        self._modules.add(module_name_of(path))

        for name, kind in BindingCollector().collect(tree):
            self._module_kinds.setdefault(name, set()).add(kind)

        for node in ast.walk(tree):
            self._learn_from(node)

    def module_constant(self, name: str) -> str:
        return kind_of(self._module_kinds.get(name, set()))

    def class_constant(self, class_name: str, name: str) -> str:
        if name in self._attribute_targets:
            return ""

        return kind_of(self._class_kinds.get(f"{class_name}.{name}", set()))

    def is_class(self, name: str) -> bool:
        return name in self._classes

    def is_module(self, name: str) -> bool:
        return name in self._modules

    def _learn_from(self, node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            self._learn_class(node)
        elif isinstance(node, ast.Global):
            for name in node.names:
                self._module_kinds.setdefault(name, set()).add("")
        elif isinstance(node, ast.Attribute) and isinstance(
            node.ctx, ast.Store | ast.Del
        ):
            self._attribute_targets.add(node.attr)

    def _learn_class(self, class_node: ast.ClassDef) -> None:
        plain = is_plain_class(class_node)
        self._classes.add(class_node.name)

        for name, kind in BindingCollector().collect(class_node):
            key = f"{class_node.name}.{name}"
            self._class_kinds.setdefault(key, set()).add(kind if plain else "")


class FileComparisons:
    def __init__(self, path: str, constants: ProjectConstants) -> None:
        self._path: str = path
        self._constants: ProjectConstants = constants

    def find_in(self, tree: ast.Module) -> list[IdentityComparison]:
        context = ScopeContext(
            frozenset(), bound_names(tree), "", {}, value_subjects_in(tree)
        )
        return self._find_in_scope(tree, context)

    def _find_in_scope(
        self, scope: ast.AST, context: ScopeContext
    ) -> list[IdentityComparison]:
        found: list[IdentityComparison] = []

        for node in scope_nodes(scope):
            if isinstance(node, LOCAL_SCOPE_NODES):
                found.extend(self._find_in_function(node, context))
            elif isinstance(node, ast.ClassDef):
                inner = context._replace(class_name=node.name)
                found.extend(self._find_in_scope(node, inner))
            elif isinstance(node, ast.Compare):
                found.extend(self._mistakes_in(node, context))

        return found

    def _find_in_function(
        self, function: LocalScope, context: ScopeContext
    ) -> list[IdentityComparison]:
        inner = context._replace(
            local_names=context.local_names | bound_names(function),
            sentinels=context.sentinels | sentinels_of(function),
            value_subjects=value_subjects_in(function),
        )

        return self._find_in_scope(function, inner)

    def _mistakes_in(
        self, comparison: ast.Compare, context: ScopeContext
    ) -> list[IdentityComparison]:
        found: list[IdentityComparison] = []
        left = comparison.left

        for operator, right in zip(
            comparison.ops, comparison.comparators, strict=True
        ):
            replacement = EQUALITY_FOR.get(type(operator), "")
            reason = replacement and self._pair_reason(left, right, context)

            if reason:
                pair = ast.Compare(left, [operator], [right])
                found.append(
                    IdentityComparison(
                        self._path,
                        left.lineno,
                        ast.unparse(pair),
                        reason,
                        replacement,
                    )
                )

            left = right

        return found

    def _pair_reason(
        self, left: ast.expr, right: ast.expr, context: ScopeContext
    ) -> str:
        has_literal = any(
            isinstance(side, ast.Constant)
            or dotted_name(side) in SINGLETON_NAMES
            for side in (left, right)
        )

        if has_literal or is_sentinel_check(left, right, context.sentinels):
            return ""

        return self._value_reason(left, right, context) or (
            self._value_reason(right, left, context)
        )

    def _value_reason(
        self, side: ast.expr, other: ast.expr, context: ScopeContext
    ) -> str:
        kind = self._constant_kind(side, context)
        compared_by_value = ast.dump(other) in context.value_subjects

        if kind and compared_by_value:
            return f"{ast.unparse(side)} is a constant {kind}"

        if self._makes_new_value(side, context):
            return f"{ast.unparse(side)} makes a new value"

        return ""

    def _constant_kind(self, side: ast.expr, context: ScopeContext) -> str:
        if isinstance(side, ast.Name):
            return self._name_kind(side.id, context)

        if isinstance(side, ast.Attribute):
            return self._attribute_kind(side, context)

        return ""

    def _name_kind(self, name: str, context: ScopeContext) -> str:
        if name in context.local_names or name not in context.module_names:
            return ""

        return self._constants.module_constant(name)

    def _attribute_kind(
        self, attribute: ast.Attribute, context: ScopeContext
    ) -> str:
        owner = dotted_name(attribute.value)
        owner_name = owner.rpartition(".")[2]

        if owner in INSTANCE_NAMES and context.class_name:
            owner_name = context.class_name
        elif owner in context.local_names:
            return ""

        if self._constants.is_class(owner_name):
            return self._constants.class_constant(owner_name, attribute.attr)

        if self._constants.is_module(owner_name):
            return self._constants.module_constant(attribute.attr)

        return ""

    def _makes_new_value(self, side: ast.expr, context: ScopeContext) -> bool:
        if isinstance(side, ast.JoinedStr):
            return True

        if not isinstance(side, ast.Call):
            return False

        callee = side.func

        if isinstance(callee, ast.Attribute):
            return callee.attr in FRESH_METHODS

        callee_name = dotted_name(callee)
        shadowed = (
            callee_name in context.local_names
            or callee_name in context.module_names
        )

        return callee_name in FRESH_BUILTINS and not shadowed


class IdentityComparisons:
    def find_in(self, paths: list[str]) -> list[IdentityComparison]:
        trees: dict[str, ast.Module] = {}
        constants = ProjectConstants()

        for path in paths:
            trees[path] = ast.parse(Path(path).read_bytes(), path)
            constants.learn(path, trees[path])

        found: set[IdentityComparison] = set()

        for path, tree in trees.items():
            found.update(FileComparisons(path, constants).find_in(tree))

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for mistake in IdentityComparisons().find_in(source_paths):
    location = f"{mistake.path}:{mistake.line_number}"
    problem = (
        f"{mistake.comparison} compares object identity, but {mistake.reason}"
    )
    fix = f"equal values can be distinct objects, so use {mistake.replacement}"
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
