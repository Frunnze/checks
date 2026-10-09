import ast

from factory_dependencies import abstract_classes
from python_structure_types import Module

_FACTORY_VERBS = ("build", "create", "get", "make", "resolve")


def classes_in(tree: ast.Module) -> list[ast.ClassDef]:
    return [node for node in tree.body if isinstance(node, ast.ClassDef)]


def class_bases(modules: list[Module]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}

    for module in modules:
        for node in classes_in(module.tree):
            direct = {
                name
                for base in node.bases
                if (name := expression_name(base)) is not None
            }
            found.setdefault(node.name, set()).update(direct)

    return found


def declared_abstractions(modules: list[Module]) -> set[str]:
    found: set[str] = set()

    for module in modules:
        found.update(abstract_classes(module.tree))

    return found


def is_factory_method(owner: str, method: str) -> bool:
    if method.startswith("_"):
        return False

    return owner.casefold().endswith("factory") or method.startswith(
        _FACTORY_VERBS
    )


def annotation_name(annotation: ast.expr | None) -> str | None:
    if not isinstance(annotation, (ast.Name, ast.Attribute)):
        return None

    return expression_name(annotation)


def returned_constructors(scope: ast.AST) -> set[str]:
    found: set[str] = set()

    for node in ast.walk(scope):
        if not isinstance(node, ast.Return) or not isinstance(
            node.value, ast.Call
        ):
            continue

        name = expression_name(node.value.func)

        if name is not None and name.rsplit(".", 1)[-1][:1].isupper():
            found.add(name.rsplit(".", 1)[-1])

    return found


def inherits(
    concrete: str, abstraction: str, bases: dict[str, set[str]]
) -> bool:
    pending = [concrete]
    visited: set[str] = set()

    while pending:
        current = pending.pop()

        if current in visited:
            continue

        visited.add(current)
        direct = bases.get(current, set())

        if abstraction in direct:
            return True

        pending.extend(direct)

    return False


def expression_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = expression_name(node.value)
        return node.attr if owner is None else f"{owner}.{node.attr}"

    return None
