import ast
from pathlib import Path

from factory_hierarchy import class_bases, classes_in
from python_structure_types import Module

_COMPOSITION_MODULES = ("app_factory.py", "main.py")
_COMPOSITION_OWNERS = ("factory", "builder", "container")


def collaborator_names(modules: list[Module]) -> set[str]:
    behaving = _behaving_classes(modules)
    bases = class_bases(modules)
    found: set[str] = set()

    for name in bases:
        if _lineage(name, bases) & behaving:
            found.add(name)

    return found


def wires_dependencies(path: str, owner_name: str) -> bool:
    if Path(path).name in _COMPOSITION_MODULES:
        return True

    return owner_name.casefold().endswith(_COMPOSITION_OWNERS)


def _behaving_classes(modules: list[Module]) -> set[str]:
    found: set[str] = set()

    for module in modules:
        for owner in classes_in(module.tree):
            if _has_public_behavior(owner):
                found.add(owner.name)

    return found


def _lineage(name: str, bases: dict[str, set[str]]) -> set[str]:
    pending = [name]
    visited: set[str] = set()

    while pending:
        current = pending.pop()

        if current in visited:
            continue

        visited.add(current)

        for base in bases.get(current, set()):
            pending.append(base.rsplit(".", 1)[-1])

    return visited


def _has_public_behavior(owner: ast.ClassDef) -> bool:
    return any(
        isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not member.name.startswith("_")
        for member in owner.body
    )
