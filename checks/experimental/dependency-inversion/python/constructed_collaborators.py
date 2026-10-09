import ast
import sys

from collaborator_classes import collaborator_names, wires_dependencies
from dependency_inversion_findings import (
    ConstructedCollaborator,
    message_for,
)
from factory_dependencies import constructed_dependencies
from factory_hierarchy import classes_in
from python_structure_types import Module, modules_from


def constructed_collaborators(
    paths: list[str],
) -> list[ConstructedCollaborator]:
    modules = modules_from(paths)
    collaborators = collaborator_names(modules)
    found: list[ConstructedCollaborator] = []

    for module in modules:
        found.extend(_module_findings(module, collaborators))

    return sorted(found)


def _module_findings(
    module: Module, collaborators: set[str]
) -> list[ConstructedCollaborator]:
    found: list[ConstructedCollaborator] = []

    for owner in classes_in(module.tree):
        if wires_dependencies(module.path, owner.name):
            continue

        finding = _owner_finding(module.path, owner, collaborators)

        if finding is not None:
            found.append(finding)

    return found


def _owner_finding(
    path: str, owner: ast.ClassDef, collaborators: set[str]
) -> ConstructedCollaborator | None:
    constructor = _constructor_of(owner)

    if constructor is None:
        return None

    constructed = constructed_dependencies(constructor) & collaborators

    if not constructed:
        return None

    return ConstructedCollaborator(
        path, constructor.lineno, owner.name, tuple(sorted(constructed))
    )


def _constructor_of(owner: ast.ClassDef) -> ast.FunctionDef | None:
    for member in owner.body:
        if isinstance(member, ast.FunctionDef) and member.name == "__init__":
            return member

    return None


def main() -> None:
    source_paths = sys.stdin.read().split()

    for finding in constructed_collaborators(source_paths):
        _ = sys.stdout.write(
            f"{finding.path}:{finding.line_number}: "
            f"{message_for(finding)}\n"
        )


if __name__ == "__main__":
    main()
