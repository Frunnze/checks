import ast
import sys
from pathlib import Path

from concrete_type_comparisons import ConcreteTypeComparisons
from enum_comparisons import EnumComparisons, enum_members
from ocp_findings import (
    FUNCTION_NODES,
    ClosedFactory,
    ConcreteFactoryDependency,
    ConcreteTypeDispatch,
    EnumDispatch,
    Finding,
    ScatteredVariantDispatch,
    VariantDispatch,
)
from python_structure_types import Module, modules_from
from python_structures import structural_findings
from scattered_comparisons import scattered_comparisons, top_level_scopes
from standard_input import paths_from_standard_input
from string_comparisons import StringComparisons


class VariantDispatches:
    def find_in(self, paths: list[str]) -> list[Finding]:
        modules = modules_from(paths)
        enums = enum_members([module.tree for module in modules])
        found: list[Finding] = [*structural_findings(modules)]

        for module in modules:
            found.extend(self._find_in_module(module, enums))

        return sorted(found)

    def _find_in_module(
        self, module: Module, enums: dict[str, set[str]]
    ) -> list[Finding]:
        path = str(Path(module.path))
        constants = module.constants
        found: list[Finding] = list(
            scattered_comparisons(
                path, top_level_scopes(module.tree), constants
            )
        )

        for scope in ast.walk(module.tree):
            if isinstance(scope, FUNCTION_NODES):
                found.extend(_scope_findings(path, scope, constants, enums))

        return found


Scope = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda


def _scope_findings(
    path: str,
    scope: Scope,
    constants: dict[str, str],
    enums: dict[str, set[str]],
) -> list[Finding]:
    name = getattr(scope, "name", "(anonymous)")
    line = scope.lineno
    strings = StringComparisons(scope, constants)
    strings.visit(scope)

    found: list[Finding] = [
        VariantDispatch(path, line, name, subject, variants)
        for _, subject, variants in strings.collected()
    ]

    return [*found, *_type_findings(path, line, name, scope, enums)]


def _type_findings(
    path: str, line: int, name: str, scope: Scope, enums: dict[str, set[str]]
) -> list[Finding]:
    types = ConcreteTypeComparisons(scope)
    types.visit(scope)
    members = EnumComparisons(scope, enums)
    members.visit(scope)

    found: list[Finding] = [
        ConcreteTypeDispatch(path, line, name, subject, concrete)
        for subject, concrete in types.collected()
    ]
    found.extend(
        EnumDispatch(path, line, name, subject, variants)
        for subject, variants in members.collected()
    )

    return found


def message_for(dispatch: Finding) -> str:
    if isinstance(dispatch, VariantDispatch):
        values = ", ".join(dispatch.variants)
        return (
            f"{dispatch.function_name} compares {dispatch.subject} to "
            f"{len(dispatch.variants)} strings: {values}"
        )
    if isinstance(dispatch, EnumDispatch):
        values = ", ".join(dispatch.members)
        return (
            f"{dispatch.function_name} compares {dispatch.subject} to "
            f"{len(dispatch.members)} enum members: {values}"
        )
    if isinstance(dispatch, ConcreteTypeDispatch):
        values = ", ".join(dispatch.concrete_types)
        return (
            f"{dispatch.function_name} dispatches {dispatch.subject} across "
            f"{len(dispatch.concrete_types)} concrete types: {values}"
        )
    if isinstance(dispatch, ScatteredVariantDispatch):
        values = ", ".join(dispatch.variants)
        return (
            f"{dispatch.subject} dispatch is scattered across "
            f"{dispatch.function_count} functions, starting at "
            f"{dispatch.function_name}: {values}"
        )
    if isinstance(dispatch, ClosedFactory):
        values = ", ".join(dispatch.implementations)
        return (
            f"{dispatch.function_name} closes {dispatch.abstraction} over "
            f"concrete implementations: {values}"
        )
    if isinstance(dispatch, ConcreteFactoryDependency):
        values = ", ".join(dispatch.dependencies)
        return (
            f"{dispatch.factory_name} leaks concrete dependencies while "
            f"creating {dispatch.abstraction}: {values}"
        )

    return (
        f"{dispatch.axis} behavior is split across "
        f"{len(dispatch.registry_names)} registries in "
        f"{dispatch.file_count} "
        f"{'file' if dispatch.file_count == 1 else 'files'}: "
        f"{', '.join(dispatch.registry_names)}"
    )


def main() -> None:
    source_paths = paths_from_standard_input()

    for dispatch in VariantDispatches().find_in(source_paths):
        _ = sys.stdout.write(
            f"{dispatch.path}:{dispatch.line_number}: "
            f"{message_for(dispatch)}\n"
        )


if __name__ == "__main__":
    main()
