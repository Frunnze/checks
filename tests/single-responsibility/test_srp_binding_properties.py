import ast
import keyword

from hypothesis import given
from hypothesis import strategies as st
from srp_support import effect_domains

from python_bindings import (
    CLIENT_FACTORY_OPERATIONS,
    assigned_value,
    called_client_type,
    local_bindings,
    module_bindings,
    qualified,
    returned_type_bindings,
)
from python_fields import class_fields
from python_qualified_names import divided_path_type

IDENTIFIER = st.from_regex(r"[a-z][a-z_]{0,8}", fullmatch=True).filter(
    lambda name: not keyword.iskeyword(name)
)
LIBRARY_IMPORTS = {"sqlite3": "sqlite3", "OpenAI": "openai.OpenAI"}
CATALOGUED_TYPES = st.sampled_from(["sqlite3.Connection", "OpenAI"])


def parsed_expression(source: str) -> ast.expr:
    return ast.parse(source, mode="eval").body


def parsed_statement(source: str) -> ast.stmt:
    return ast.parse(source).body[0]


@given(st.lists(IDENTIFIER, min_size=1, max_size=4), IDENTIFIER)
def test_qualified_property_path_division_keeps_the_path_lineage(
    segments, operation
):
    divided_path = " / ".join(["directory", *segments])
    expression = parsed_expression(f"({divided_path}).{operation}")
    path_bindings = {"directory": "pathlib.Path"}

    assert qualified(expression, path_bindings) == "pathlib.Path." + operation


@given(st.lists(IDENTIFIER, min_size=1, max_size=4), IDENTIFIER)
def test_qualified_property_division_of_unknown_values_stays_unresolved(
    segments, operation
):
    divided_value = " / ".join(["count", *segments])
    expression = parsed_expression(f"({divided_value}).{operation}")

    assert qualified(expression, {}) == ""


@given(IDENTIFIER, st.sampled_from(sorted(CLIENT_FACTORY_OPERATIONS)))
def test_assigned_value_property_awaiting_a_factory_binds_like_the_factory(
    module, operation
):
    library_bindings = {module: "library_" + module}
    factory_call = parsed_expression(f"{module}.{operation}()")
    awaited_call = ast.Await(value=factory_call)

    expected_client = f"library_{module}.{operation}"
    assert assigned_value(factory_call, library_bindings) == expected_client
    assert assigned_value(awaited_call, library_bindings) == expected_client


@given(IDENTIFIER, IDENTIFIER)
def test_assigned_value_property_annotated_factories_bind_their_return_type(
    receiver, factory
):
    factory_call = parsed_expression(f"{receiver}.{factory}()")
    returned_types = {f"{receiver}.{factory}()": "sqlite3.Connection"}

    bound_client = assigned_value(factory_call, returned_types)

    assert bound_client == "sqlite3.Connection"


@given(IDENTIFIER, CATALOGUED_TYPES)
def test_returned_type_bindings_property_binds_catalogued_return_types(
    factory, annotation
):
    module = ast.parse(f"def {factory}() -> {annotation}:\n    pass\n")

    returned_types = returned_type_bindings(module, LIBRARY_IMPORTS)

    expected_type = LIBRARY_IMPORTS.get(annotation, annotation)
    assert returned_types == {factory + "()": expected_type}


@given(IDENTIFIER, st.sampled_from(["int", "dict[str, int]", "None", "Row"]))
def test_returned_type_bindings_property_ignores_uncatalogued_types(
    factory, annotation
):
    module = ast.parse(f"def {factory}() -> {annotation}:\n    pass\n")

    assert returned_type_bindings(module, LIBRARY_IMPORTS) == {}


@given(IDENTIFIER)
def test_local_bindings_property_nested_factories_expose_their_type(factory):
    outer = parsed_statement(
        f"def outer():\n    def {factory}() -> sqlite3.Connection:\n"
        "        pass\n"
    )

    scope_bindings = local_bindings(outer, LIBRARY_IMPORTS)

    assert scope_bindings[factory + "()"] == "sqlite3.Connection"


@given(IDENTIFIER, IDENTIFIER)
def test_class_fields_property_factory_methods_bind_constructor_fields(
    field, factory
):
    writer = parsed_statement(
        "class Writer:\n"
        "    def __init__(self):\n"
        f"        self.{field}_client = self.{factory}_build()\n"
        f"    def {factory}_build(self) -> OpenAI:\n"
        "        pass\n"
    )

    fields = class_fields(writer, LIBRARY_IMPORTS)

    assert fields[field + "_client"] == "openai.OpenAI"
    assert fields[factory + "_build()"] == "openai.OpenAI"
    completion_call = fields[field + "_client"] + ".chat.completions.create"
    assert list(effect_domains([completion_call])) == ["ai"]


@given(IDENTIFIER, IDENTIFIER)
def test_called_client_type_property_plain_helpers_stay_unbound(
    module, helper
):
    helper_call = parsed_expression(f"{module}.{helper}_helper()")
    library_bindings = {module: "library_" + module}

    assert called_client_type(helper_call, library_bindings) == ""


@given(IDENTIFIER, st.sampled_from(["//", "*", "+", "%"]))
def test_divided_path_type_property_only_division_joins_paths(
    segment, operator
):
    joined = parsed_expression(f"directory {operator} {segment}")
    path_bindings = {"directory": "pathlib.Path"}

    expected_type = "pathlib.Path" if operator == "/" else ""
    assert divided_path_type(joined, path_bindings) == expected_type


@given(IDENTIFIER)
def test_module_bindings_property_binds_open_and_factory_returns(
    factory_name: str,
) -> None:
    module_source = (
        "import sqlite3\n"
        f"def {factory_name}() -> sqlite3.Connection:\n"
        "    return sqlite3.connect('store.db')\n"
    )

    bindings = module_bindings(ast.parse(module_source))

    assert bindings["open"] == "builtins.open"
    assert bindings["sqlite3"] == "sqlite3"
    assert "sqlite3.Connection" in bindings.values()
