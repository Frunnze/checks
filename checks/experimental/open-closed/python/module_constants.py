import ast
from pathlib import Path

from python_ast_values import enum_classes

_PACKAGE_MODULE = "__init__"
_STAR_IMPORT = "*"
_PRIVATE_PREFIX = "_"

ParsedModule = tuple[str, ast.Module]


def resolved_constants(parsed: list[ParsedModule]) -> list[dict[str, str]]:
    own = [string_constants(tree) for _path, tree in parsed]
    resolved = own

    for _pass in range(len(parsed)):
        exported: dict[Path, dict[str, str]] = {}

        for (path, _tree), constants in zip(parsed, resolved, strict=True):
            exported[module_location(path)] = constants

        following: list[dict[str, str]] = []

        for (path, tree), constants in zip(parsed, own, strict=True):
            imported = imported_constants(path, tree, exported)
            following.append({**imported, **constants})

        if following == resolved:
            break

        resolved = following

    return resolved


def string_constants(tree: ast.Module) -> dict[str, str]:
    found = _assigned_strings(tree.body)

    for name, owner in enum_classes(tree):
        for member, value in _assigned_strings(owner.body).items():
            found[f"{name}.{member}"] = value

    return found


def module_location(path: str) -> Path:
    location = Path(path).with_suffix("")

    return location.parent if location.name == _PACKAGE_MODULE else location


def imported_constants(
    path: str, tree: ast.Module, exported: dict[Path, dict[str, str]]
) -> dict[str, str]:
    found: dict[str, str] = {}

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                module = _imported_module(path, alias.name, 0, exported)
                found.update(_prefixed(module, alias.asname or alias.name))
        if not isinstance(statement, ast.ImportFrom):
            continue

        source = _imported_module(
            path, statement.module, statement.level, exported
        )

        for alias in statement.names:
            submodule = _imported_module(
                path,
                _joined(statement.module, alias.name),
                statement.level,
                exported,
            )
            found.update(_renamed(source, alias))
            found.update(_prefixed(submodule, alias.asname or alias.name))

    return found


def _joined(package: str | None, name: str) -> str:
    return name if package is None else f"{package}.{name}"


def _prefixed(constants: dict[str, str], prefix: str) -> dict[str, str]:
    found: dict[str, str] = {}

    for name, value in constants.items():
        found[f"{prefix}.{name}"] = value

    return found


def _imported_module(
    path: str,
    module: str | None,
    level: int,
    exported: dict[Path, dict[str, str]],
) -> dict[str, str]:
    parts = module.split(".") if module else []
    parents = list(Path(path).parents)
    roots = parents if level == 0 else parents[level - 1 : level]

    for root in roots:
        location = root.joinpath(*parts)

        if location in exported:
            return exported[location]

    return {}


def _renamed(constants: dict[str, str], alias: ast.alias) -> dict[str, str]:
    if alias.name == _STAR_IMPORT:
        return _public(constants)

    local_name = alias.asname or alias.name
    prefix = f"{alias.name}."
    found: dict[str, str] = {}

    for name, value in constants.items():
        if name == alias.name:
            found[local_name] = value
        elif name.startswith(prefix):
            found[f"{local_name}.{name.removeprefix(prefix)}"] = value

    return found


def _public(constants: dict[str, str]) -> dict[str, str]:
    found: dict[str, str] = {}

    for name, value in constants.items():
        if not name.startswith(_PRIVATE_PREFIX):
            found[name] = value

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
