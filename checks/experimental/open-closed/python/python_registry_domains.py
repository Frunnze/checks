import ast

from python_ast_values import string_value

_PREFERRED_KEYS = [
    "kind",
    "type",
    "name",
    "id",
    "choice",
    "tone",
    "status",
    "scope",
    "variant",
]


def registry_domain(
    value: ast.AST, constants: dict[str, str]
) -> set[str] | None:
    if isinstance(value, ast.Dict):
        keys = {
            resolved
            for key in value.keys
            if key is not None
            if (resolved := string_value(key, constants)) is not None
        }

        return keys if len(keys) == len(value.keys) else None

    if not isinstance(value, (ast.List, ast.Tuple)) or len(value.elts) < 3:
        return None

    strings = {
        resolved
        for element in value.elts
        if (resolved := string_value(element, constants)) is not None
    }

    if len(strings) == len(value.elts):
        return strings
    if all(isinstance(element, ast.Dict) for element in value.elts):
        domain = _dictionary_descriptor_domain(value.elts, constants)

        if domain is not None:
            return domain
    if all(isinstance(element, ast.Call) for element in value.elts):
        return _call_descriptor_domain(value.elts, constants)

    return None


def contains_behavior(
    node: ast.AST, constants: dict[str, str]
) -> bool:
    if isinstance(node, (ast.Lambda, ast.Call, ast.Attribute)):
        return True
    if isinstance(node, ast.Name):
        return node.id not in constants
    if isinstance(node, ast.Dict):
        return any(contains_behavior(value, constants) for value in node.values)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(contains_behavior(value, constants) for value in node.elts)

    return False


def _dictionary_descriptor_domain(
    elements: list[ast.expr], constants: dict[str, str]
) -> set[str] | None:
    dictionaries = [element for element in elements if isinstance(element, ast.Dict)]

    for candidate in _descriptor_keys(dictionaries[0]):
        values = {
            resolved
            for dictionary in dictionaries
            if (
                resolved := _dict_string_value(
                    dictionary, candidate, constants
                )
            )
            is not None
        }

        if len(values) == len(dictionaries):
            return values

    return None


def _call_descriptor_domain(
    elements: list[ast.expr], constants: dict[str, str]
) -> set[str] | None:
    calls = [element for element in elements if isinstance(element, ast.Call)]
    values = {
        resolved
        for call in calls
        if call.args
        if (resolved := string_value(call.args[0], constants)) is not None
    }

    return values if len(values) == len(calls) else None


def _descriptor_keys(dictionary: ast.Dict) -> list[str]:
    keys = [
        key.value
        for key in dictionary.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]

    return [
        *[key for key in _PREFERRED_KEYS if key in keys],
        *[key for key in keys if key not in _PREFERRED_KEYS],
    ]


def _dict_string_value(
    dictionary: ast.Dict, key_name: str, constants: dict[str, str]
) -> str | None:
    for key, value in zip(dictionary.keys, dictionary.values, strict=True):
        if isinstance(key, ast.Constant) and key.value == key_name:
            return string_value(value, constants)

    return None
