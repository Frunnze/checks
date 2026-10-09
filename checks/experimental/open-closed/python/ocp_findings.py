import ast
from typing import NamedTuple

MAXIMUM_VARIANTS = 2
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
EQUALITY_NODES = (ast.Eq, ast.NotEq)
MEMBERSHIP_NODES = (ast.In, ast.NotIn)
TYPE_EQUALITY_NODES = (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)


class VariantDispatch(NamedTuple):
    path: str
    line_number: int
    function_name: str
    subject: str
    variants: tuple[str, ...]


class EnumDispatch(NamedTuple):
    path: str
    line_number: int
    function_name: str
    subject: str
    members: tuple[str, ...]


class ConcreteTypeDispatch(NamedTuple):
    path: str
    line_number: int
    function_name: str
    subject: str
    concrete_types: tuple[str, ...]


class ScatteredVariantDispatch(NamedTuple):
    path: str
    line_number: int
    function_name: str
    subject: str
    variants: tuple[str, ...]
    function_count: int


class ClosedFactory(NamedTuple):
    path: str
    line_number: int
    function_name: str
    abstraction: str
    implementations: tuple[str, ...]


class ConcreteFactoryDependency(NamedTuple):
    path: str
    line_number: int
    factory_name: str
    abstraction: str
    dependencies: tuple[str, ...]


class FragmentedRegistry(NamedTuple):
    path: str
    line_number: int
    axis: str
    registry_names: tuple[str, ...]
    file_count: int


Finding = (
    VariantDispatch
    | EnumDispatch
    | ConcreteTypeDispatch
    | ScatteredVariantDispatch
    | ClosedFactory
    | ConcreteFactoryDependency
    | FragmentedRegistry
)
