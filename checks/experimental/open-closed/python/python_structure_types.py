import ast
from dataclasses import dataclass
from pathlib import Path

from module_constants import string_constants
from python_ast_values import (
    assigned_name,
    expression_name,
    inherits_from,
    literal_annotation,
    string_value,
)

_MAPPING_NAMES = {"dict", "Dict", "Mapping", "MutableMapping"}


@dataclass(frozen=True)
class Axis:
    name: str
    domain: frozenset[str]


@dataclass(frozen=True)
class Registry:
    path: str
    line_number: int
    name: str
    axis: Axis
    is_behavior: bool


@dataclass(frozen=True)
class Module:
    path: str
    tree: ast.Module
    constants: dict[str, str]


def modules_from(paths: list[str]) -> list[Module]:
    return [
        Module(
            path,
            tree := ast.parse(Path(path).read_text(encoding="utf-8")),
            string_constants(tree),
        )
        for path in paths
    ]


def _add_axis(
    found: dict[str, list[Axis]], name: str, domain: set[str]
) -> None:
    if len(domain) < 2:
        return

    axis = Axis(name, frozenset(domain))
    if axis not in found.setdefault(name, []):
        found[name].append(axis)


def axes_in(modules: list[Module]) -> dict[str, list[Axis]]:
    found: dict[str, list[Axis]] = {}

    for module in modules:
        for node in module.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                name = assigned_name(node)
                value = node.value

                if name is not None and value is not None:
                    domain = literal_annotation(value)

                    if domain is not None:
                        _add_axis(found, name, domain)
            elif isinstance(node, ast.ClassDef) and inherits_from(
                node, {"Enum", "StrEnum"}
            ):
                values = {
                    value
                    for member in node.body
                    if isinstance(member, (ast.Assign, ast.AnnAssign))
                    if (value := string_value(member.value, module.constants))
                    is not None
                }
                _add_axis(found, node.name, values)

    return found


def mapping_axis(
    annotation: ast.AST, axes: dict[str, list[Axis]]
) -> Axis | None:
    if not isinstance(annotation, ast.Subscript):
        return None
    if expression_name(annotation.value).rsplit(".", 1)[-1] not in _MAPPING_NAMES:
        return None

    arguments = (
        annotation.slice.elts
        if isinstance(annotation.slice, ast.Tuple)
        else [annotation.slice]
    )

    if not arguments:
        return None

    return axis_from_annotation(arguments[0], axes)


def axis_from_annotation(
    annotation: ast.AST, axes: dict[str, list[Axis]]
) -> Axis | None:
    domain = literal_annotation(annotation)

    if domain is not None:
        return Axis("Literal", frozenset(domain))

    name = expression_name(annotation).rsplit(".", 1)[-1]
    candidates = axes.get(name, [])

    return candidates[0] if len(candidates) == 1 else None


def axis_for_domain(
    domain: set[str], axes: dict[str, list[Axis]]
) -> Axis | None:
    matches = [
        axis
        for candidates in axes.values()
        for axis in candidates
        if axis.domain == frozenset(domain)
    ]

    return min(matches, key=lambda axis: axis.name) if matches else None
