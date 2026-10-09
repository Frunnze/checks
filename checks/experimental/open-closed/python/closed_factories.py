import ast

from factory_dependencies import constructed_dependencies
from factory_hierarchy import (
    annotation_name,
    class_bases,
    classes_in,
    declared_abstractions,
    inherits,
    is_factory_method,
    returned_constructors,
)
from ocp_findings import ClosedFactory, ConcreteFactoryDependency
from python_structure_types import Module

Factory = ClosedFactory | ConcreteFactoryDependency


def closed_factories(modules: list[Module]) -> list[Factory]:
    bases = class_bases(modules)
    abstractions = declared_abstractions(modules)
    found: list[Factory] = []

    for module in modules:
        for owner in classes_in(module.tree):
            found.extend(
                _factory_findings(module.path, owner, bases, abstractions)
            )

    return sorted(found)


def _factory_findings(
    path: str,
    owner: ast.ClassDef,
    bases: dict[str, set[str]],
    abstractions: set[str],
) -> list[Factory]:
    found: list[Factory] = []
    produced: set[str] = set()

    for method in _factory_methods(owner):
        abstraction = annotation_name(method.returns)

        if abstraction is None:
            continue

        if abstraction in abstractions:
            produced.add(abstraction)

        closed = _closed_factory(path, method, abstraction, bases)

        if closed is not None:
            found.append(closed)

    leak = _dependency_leak(path, owner, produced)

    return found if leak is None else [*found, leak]


def _factory_methods(
    owner: ast.ClassDef,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        method
        for method in owner.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
        and is_factory_method(owner.name, method.name)
    ]


def _closed_factory(
    path: str,
    method: ast.FunctionDef | ast.AsyncFunctionDef,
    abstraction: str,
    bases: dict[str, set[str]],
) -> ClosedFactory | None:
    implementations = tuple(
        sorted(
            concrete
            for concrete in returned_constructors(method)
            if concrete != abstraction
            and inherits(concrete, abstraction, bases)
        )
    )

    if not implementations:
        return None

    return ClosedFactory(
        path, method.lineno, method.name, abstraction, implementations
    )


def _dependency_leak(
    path: str, owner: ast.ClassDef, produced: set[str]
) -> ConcreteFactoryDependency | None:
    if not produced:
        return None

    constructor = next(
        (
            method
            for method in owner.body
            if isinstance(method, ast.FunctionDef)
            and method.name == "__init__"
        ),
        None,
    )

    if constructor is None:
        return None

    dependencies = constructed_dependencies(constructor)

    if not dependencies:
        return None

    return ConcreteFactoryDependency(
        path,
        constructor.lineno,
        owner.name,
        ", ".join(sorted(produced)),
        tuple(sorted(dependencies)),
    )
