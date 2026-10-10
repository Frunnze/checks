import ast
from pathlib import Path

from python_ast_values import enum_classes

_PACKAGE_MODULE = "__init__"


def string_constants(tree: ast.Module) -> dict[str, str]:
    found = _assigned_strings(tree.body)

    for owner in enum_classes(tree):
        for member, value in _assigned_strings(owner.body).items():
            found[f"{owner.name}.{member}"] = value

    return found


def module_location(path: str) -> Path:
    location = Path(path).with_suffix("")

    return location.parent if location.name == _PACKAGE_MODULE else location


def imported_constants(
    path: str, tree: ast.Module, exported: dict[Path, dict[str, str]]
) -> dict[str, str]:
    found: dict[str, str] = {}

    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom):
            continue

        source = _imported_module(path, statement, exported)

        for alias in statement.names:
            found.update(_renamed(source, alias))

    return found


def _imported_module(
    path: str, statement: ast.ImportFrom, exported: dict[Path, dict[str, str]]
) -> dict[str, str]:
    parts = statement.module.split(".") if statement.module else []
    parents = list(Path(path).parents)
    roots = (
        parents
        if statement.level == 0
        else parents[statement.level - 1 : statement.level]
    )

    for root in roots:
        location = root.joinpath(*parts)

        if location in exported:
            return exported[location]

    return {}


def _renamed(constants: dict[str, str], alias: ast.alias) -> dict[str, str]:
    local_name = alias.asname or alias.name
    prefix = f"{alias.name}."
    found: dict[str, str] = {}

    for name, value in constants.items():
        if name == alias.name:
            found[local_name] = value
        elif name.startswith(prefix):
            found[f"{local_name}.{name.removeprefix(prefix)}"] = value

    return found


def _assigned_strings(body: list[ast.stmt]) -> dict[str, str]:
    found: dict[str, str] = {}

    for statement in body:
        if isinstance(statement, ast.Assign):
            _record_assignment(found, statement.targets, statement.value)
        elif isinstance(statement, ast.AnnAssign):
            _record_assignment(found, (statement.target,), statement.value)

    return found


def _record_assignment(
    found: dict[str, str], targets: tuple[ast.expr, ...] | list[ast.expr],
    value: ast.expr | None,
) -> None:
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return

    for target in targets:
        if isinstance(target, ast.Name):
            found[target.id] = value.value
