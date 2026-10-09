import ast

from ocp_findings import FragmentedRegistry
from python_registry_domains import contains_behavior, registry_domain
from python_ast_values import assigned_name
from python_structure_types import (
    Axis,
    Module,
    Registry,
    axis_for_domain,
    mapping_axis,
)

_SHARED_MAJORITY = 2
_UNNAMED_AXIS = "variant"


def registries_in(
    modules: list[Module], axes: dict[str, list[Axis]]
) -> list[Registry]:
    found: list[Registry] = []

    for module in modules:
        for node in module.tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue

            name = assigned_name(node)
            value = node.value

            if name is None or value is None:
                continue

            explicit_axis = (
                mapping_axis(node.annotation, axes)
                if isinstance(node, ast.AnnAssign)
                else None
            )
            domain = registry_domain(value, module.constants)

            if explicit_axis is not None:
                domain = set(explicit_axis.domain)
            if domain is None or len(domain) < 2:
                continue

            axis = explicit_axis or axis_for_domain(domain, axes)
            found.append(
                Registry(
                    module.path,
                    node.lineno,
                    name,
                    axis or Axis(_UNNAMED_AXIS, frozenset(domain)),
                    contains_behavior(value, module.constants),
                )
            )

    return found


def fragmented_registries(
    registries: list[Registry],
) -> list[FragmentedRegistry]:
    found: list[FragmentedRegistry] = []

    for group in _grouped_by_axis(registries):
        fragmentation = _fragmentation_of(group)

        if fragmentation is not None:
            found.append(fragmentation)

    return found


def _grouped_by_axis(registries: list[Registry]) -> list[list[Registry]]:
    widest_first = sorted(
        registries,
        key=lambda registry: (
            -len(registry.axis.domain),
            sorted(registry.axis.domain),
        ),
    )
    groups: list[list[Registry]] = []

    for registry in widest_first:
        covering = _group_covering(groups, registry)

        if covering is None:
            groups.append([registry])
        else:
            covering.append(registry)

    return groups


def _group_covering(
    groups: list[list[Registry]], registry: Registry
) -> list[Registry] | None:
    for group in groups:
        if _same_axis(registry.axis, group[0].axis):
            return group

    return None


def _same_axis(narrow: Axis, wide: Axis) -> bool:
    if narrow.domain == wide.domain:
        return True
    if _named_differently(narrow, wide):
        return False

    return (
        narrow.domain <= wide.domain
        and len(narrow.domain) * _SHARED_MAJORITY > len(wide.domain)
    )


def _named_differently(narrow: Axis, wide: Axis) -> bool:
    named = {narrow.name, wide.name} - {_UNNAMED_AXIS}

    return len(named) == 2


def _fragmentation_of(group: list[Registry]) -> FragmentedRegistry | None:
    shared = min(len(registry.axis.domain) for registry in group)
    enough = len(group) >= 3 or (len(group) >= 2 and shared >= 3)

    if not enough:
        return None

    ordered = sorted(group, key=lambda item: (item.path, item.line_number))
    first = ordered[0]
    labels = sorted(
        {item.axis.name for item in group if item.axis.name != _UNNAMED_AXIS}
    )

    return FragmentedRegistry(
        first.path,
        first.line_number,
        labels[0] if labels else _UNNAMED_AXIS,
        tuple(sorted(item.name for item in group)),
        len({item.path for item in group}),
    )
