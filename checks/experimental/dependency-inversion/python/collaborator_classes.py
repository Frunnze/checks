import ast
from pathlib import Path

from factory_hierarchy import classes_in
from python_structure_types import Module

_COMPOSITION_MODULES = ("app_factory.py", "main.py")
_COMPOSITION_OWNERS = ("factory", "builder", "container")


def collaborator_names(modules: list[Module]) -> set[str]:
    found: set[str] = set()

    for module in modules:
        for owner in classes_in(module.tree):
            if _has_public_behavior(owner):
                found.add(owner.name)

    return found


def wires_dependencies(path: str, owner_name: str) -> bool:
    if Path(path).name in _COMPOSITION_MODULES:
        return True

    return owner_name.casefold().endswith(_COMPOSITION_OWNERS)


def _has_public_behavior(owner: ast.ClassDef) -> bool:
    return any(
        isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not member.name.startswith("_")
        for member in owner.body
    )
