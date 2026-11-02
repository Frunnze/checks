import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

MUTABLE_FACTORIES = frozenset(
    {
        "set",
        "list",
        "dict",
        "defaultdict",
        "deque",
        "OrderedDict",
        "Counter",
        "ChainMap",
        "bytearray",
    }
)
LITERAL_KINDS: dict[type[ast.expr], str] = {
    ast.List: "list",
    ast.ListComp: "list",
    ast.Set: "set",
    ast.SetComp: "set",
    ast.Dict: "dict",
    ast.DictComp: "dict",
}
MUTATING_METHODS = frozenset(
    {
        "add",
        "append",
        "appendleft",
        "clear",
        "difference_update",
        "discard",
        "extend",
        "extendleft",
        "insert",
        "intersection_update",
        "pop",
        "popitem",
        "popleft",
        "remove",
        "reverse",
        "sort",
        "symmetric_difference_update",
        "update",
    }
)
CLASS_VARIABLE = "ClassVar"
INSTANCE = "self"
CLASS_RECEIVERS = frozenset({"cls", "type(self)", "self.__class__"})
CLASS_LEVEL_DECORATORS = frozenset({"classmethod", "staticmethod"})
DEFAULT_COPYING_BASE_SUFFIXES = ("Model", "Settings", "Struct")
FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
SHARED_ON_PURPOSE_WORDS = frozenset(
    {"cache", "caches", "cached", "memo", "registry"}
)
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class ClassContainer(NamedTuple):
    name: str
    kind: str
    line_number: int
    is_class_variable: bool


class Mutation(NamedTuple):
    name: str
    line_number: int


class SharedContainer(NamedTuple):
    path: str
    line_number: int
    owner: str
    name: str
    kind: str
    mutation_line: int


def last_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return expression.attr

    if isinstance(expression, ast.Subscript):
        return last_name(expression.value)

    return ""


def container_kind(value: ast.expr) -> str | None:
    if type(value) in LITERAL_KINDS:
        return LITERAL_KINDS[type(value)]

    if isinstance(value, ast.Call):
        factory = last_name(value.func)

        if factory in MUTABLE_FACTORIES:
            return factory

    return None


def class_container(statement: ast.stmt) -> ClassContainer | None:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
        value = statement.value
        is_class_variable = False
    elif isinstance(statement, ast.AnnAssign) and statement.value:
        target = statement.target
        value = statement.value
        is_class_variable = last_name(statement.annotation) == CLASS_VARIABLE
    else:
        return None

    kind = container_kind(value)

    if not isinstance(target, ast.Name) or kind is None:
        return None

    return ClassContainer(
        target.id, kind, statement.lineno, is_class_variable
    )


def copies_defaults(class_node: ast.ClassDef) -> bool:
    if class_node.decorator_list:
        return True

    return any(
        last_name(base).endswith(DEFAULT_COPYING_BASE_SUFFIXES)
        for base in class_node.bases
    )


def instance_attribute(expression: ast.expr) -> str | None:
    if not isinstance(expression, ast.Attribute):
        return None

    receiver = expression.value

    if isinstance(receiver, ast.Name) and receiver.id == INSTANCE:
        return expression.attr

    return None


def mutation_of(node: ast.AST) -> Mutation | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        is_mutating = node.func.attr in MUTATING_METHODS
        name = instance_attribute(node.func.value) if is_mutating else None
    elif isinstance(node, ast.AugAssign):
        name = instance_attribute(node.target)
    else:
        return None

    if name is None:
        return None

    return Mutation(name, node.lineno)


def is_instance_method(method: FunctionNode) -> bool:
    arguments = method.args.posonlyargs + method.args.args

    for decorator in method.decorator_list:
        if last_name(decorator) in CLASS_LEVEL_DECORATORS:
            return False

    return bool(arguments) and arguments[0].arg == INSTANCE


class ClassUse:
    def __init__(self, class_node: ast.ClassDef) -> None:
        self._receivers: frozenset[str] = CLASS_RECEIVERS | {class_node.name}
        self.mutations: dict[str, int] = {}
        self.rebound: set[str] = set()
        self.through_class: set[str] = set()

        for statement in class_node.body:
            if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
                self._record_method(statement)

    def _record_method(self, method: FunctionNode) -> None:
        nodes = list(ast.walk(method))
        augmented_targets = {
            id(node.target)
            for node in nodes
            if isinstance(node, ast.AugAssign)
        }

        for node in nodes:
            is_attribute = isinstance(node, ast.Attribute)

            if is_attribute and id(node) not in augmented_targets:
                self._record_attribute(node)

        if is_instance_method(method):
            for node in nodes:
                self._record_mutation(node)

    def _record_mutation(self, node: ast.AST) -> None:
        mutation = mutation_of(node)

        if mutation is None:
            return

        earliest = self.mutations.get(mutation.name, mutation.line_number)
        self.mutations[mutation.name] = min(earliest, mutation.line_number)

    def _record_attribute(self, node: ast.Attribute) -> None:
        if ast.unparse(node.value) in self._receivers:
            self.through_class.add(node.attr)
        elif instance_attribute(node) and isinstance(node.ctx, ast.Store):
            self.rebound.add(node.attr)


def classes_outside_functions(tree: ast.Module) -> list[ast.ClassDef]:
    found: list[ast.ClassDef] = []
    pending: list[ast.AST] = [tree]

    while pending:
        node = pending.pop()

        if isinstance(node, FUNCTION_SCOPES):
            continue

        if isinstance(node, ast.ClassDef):
            found.append(node)

        pending.extend(ast.iter_child_nodes(node))

    return found


def is_named_as_shared(name: str) -> bool:
    words = {word.lower() for word in WORD_BOUNDARY.split(name) if word}
    return bool(words & SHARED_ON_PURPOSE_WORDS)


def is_accidentally_shared(
    container: ClassContainer, use: ClassUse, class_node: ast.ClassDef
) -> bool:
    if container.name not in use.mutations:
        return False

    if container.name in use.rebound | use.through_class:
        return False

    if is_named_as_shared(container.name):
        return False

    return container.is_class_variable or not copies_defaults(class_node)


class SharedContainers:
    def find_in(self, paths: list[str]) -> list[SharedContainer]:
        found: set[SharedContainer] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for class_node in classes_outside_functions(tree):
                found.update(self._find_in_class(path, class_node))

        return sorted(found)

    def _find_in_class(
        self, path: str, class_node: ast.ClassDef
    ) -> list[SharedContainer]:
        use = ClassUse(class_node)
        found: list[SharedContainer] = []

        for statement in class_node.body:
            container = class_container(statement)

            if container is None:
                continue

            if is_accidentally_shared(container, use, class_node):
                found.append(
                    SharedContainer(
                        path,
                        container.line_number,
                        class_node.name,
                        container.name,
                        container.kind,
                        use.mutations[container.name],
                    )
                )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for shared in SharedContainers().find_in(source_paths):
    location = f"{shared.path}:{shared.line_number}"
    problem = (
        f"{shared.owner}.{shared.name} is one {shared.kind} shared by every"
        f" instance, yet line {shared.mutation_line} changes it through"
        f" {INSTANCE}"
    )
    fix = (
        f"create it per instance in __init__ ({INSTANCE}.{shared.name} ="
        f" ...), or reach it through the class if sharing is intended"
    )
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
