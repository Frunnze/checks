from closed_factories import Factory, closed_factories
from ocp_findings import FragmentedRegistry
from python_registries import fragmented_registries, registries_in
from python_structure_types import axes_in, modules_from

StructuralFinding = FragmentedRegistry | Factory


def structural_findings(paths: list[str]) -> list[StructuralFinding]:
    modules = modules_from(paths)
    axes = axes_in(modules)
    registries = registries_in(modules, axes)

    return [*fragmented_registries(registries), *closed_factories(modules)]
