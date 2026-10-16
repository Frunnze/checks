import ast
import sys

from collaborator_classes import collaborator_names, wires_dependencies
from dependency_inversion_findings import (
    ConstructedCollaborator,
    message_for,
)
from factory_dependencies import (
    constructed_dependencies,
    standard_library_names,
)
from factory_hierarchy import classes_in
from python_ast_values import imported_aliases
from python_structure_types import Module, modules_from
from standard_input import paths_from_standard_input


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
    aliases = imported_aliases(module.tree)
    standard_names = standard_library_names(module.tree)
    found: list[ConstructedCollaborator] = []

    for owner in classes_in(module.tree):
        if wires_dependencies(module.path, owner.name):
            continue

        finding = _owner_finding(
            module.path, owner, collaborators, aliases, standard_names
        )

        if finding is not None:
            found.append(finding)

    return found


def _owner_finding(
    path: str,
    owner: ast.ClassDef,
    collaborators: set[str],
    aliases: dict[str, str],
    standard_names: set[str],
) -> ConstructedCollaborator | None:
    constructor = _constructor_of(owner)

    if constructor is None:
        return None

    built = constructed_dependencies(constructor, standard_names)
    constructed = {aliases.get(name, name) for name in built} & collaborators

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
    source_paths = paths_from_standard_input()

    for finding in constructed_collaborators(source_paths):
        _ = sys.stdout.write(
            f"{finding.path}:{finding.line_number}: "
            f"{message_for(finding)}\n"
        )


if __name__ == "__main__":
    main()
