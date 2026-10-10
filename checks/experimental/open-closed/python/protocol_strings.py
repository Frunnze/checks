import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from javascript_strings import decoded_javascript_string
from module_constants import string_constants
from ocp_findings import CONTAINER_NODES, IDENTITY_NODES, MEMBERSHIP_NODES
from python_structure_types import parsed_module
from standard_input import paths_from_standard_input

_ERROR_FIELDS = {"content", "detail", "error", "message", "reason"}
_ERROR_CONSTRUCTORS = ("Error", "Exception", "Response")
_PYTHON_SUFFIXES = (".py",)
_TYPESCRIPT_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")
_SOURCE_SUFFIXES = (*_PYTHON_SUFFIXES, *_TYPESCRIPT_SUFFIXES)
_CONSUMER_SUFFIXES = {
    "python": _PYTHON_SUFFIXES,
    "typescript": _TYPESCRIPT_SUFFIXES,
}
_COMMENT_START = "/"
_QUOTES = ('"', "'", "`")
_LEXICAL_TOKEN = re.compile(
    r"//[^\n]*|/\*.*?\*/"
    r'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`'
    r"|[A-Za-z_$][\w$]*",
    re.DOTALL,
)
_COMPARISON_BEFORE = re.compile(r"(?:===|!==|==|!=)\s*$")
_COMPARISON_AFTER = re.compile(r"^\s*(?:===|!==|==|!=)")
_CASE_BEFORE = re.compile(r"\bcase\s+$")
_FIELD_BEFORE = re.compile(
    r"(?:content|detail|error|message|reason)\s*:\s*$"
)
_CONSTRUCTOR_BEFORE = re.compile(
    r"(?:new\s+)?(?:[A-Za-z_$][\w$]*)?(?:Error|Exception|Response)\s*\(\s*$"
)
_CONSTANT_BEFORE = re.compile(
    r"\bconst\s+([A-Za-z_$][\w$]*)\s*(?::[^=]*)?=\s*$"
)


MessageToken = tuple[re.Match[str], str]


@dataclass(frozen=True, order=True)
class Occurrence:
    path: str
    line_number: int
    text: str


def _is_human_message(value: str) -> bool:
    return len(value) >= 12 and any(character.isspace() for character in value)


def _constant_value(
    node: ast.AST | None, constants: dict[str, str]
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)

    return None


def _python_occurrences(
    path: str, tree: ast.Module
) -> tuple[list[Occurrence], list[Occurrence]]:
    constants = string_constants(tree)
    produced: list[Occurrence] = []
    consumed: list[Occurrence] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            constructor = ast.unparse(node.func).rsplit(".", 1)[-1]

            if constructor.endswith(_ERROR_CONSTRUCTORS):
                for argument in node.args:
                    value = _constant_value(argument, constants)

                    if value is not None and _is_human_message(value):
                        produced.append(Occurrence(path, node.lineno, value))

            for keyword in node.keywords:
                if keyword.arg not in _ERROR_FIELDS:
                    continue

                value = _constant_value(keyword.value, constants)

                if value is not None and _is_human_message(value):
                    produced.append(Occurrence(path, node.lineno, value))

        if isinstance(node, ast.Dict):
            for key, value_node in zip(node.keys, node.values, strict=True):
                key_name = _constant_value(key, constants)
                value = _constant_value(value_node, constants)

                if (
                    key_name in _ERROR_FIELDS
                    and value is not None
                    and _is_human_message(value)
                ):
                    produced.append(Occurrence(path, node.lineno, value))

        if not isinstance(node, (ast.Compare, ast.MatchValue)):
            continue

        for compared in _compared_operands(node):
            value = _constant_value(compared, constants)

            if value is not None and _is_human_message(value):
                consumed.append(Occurrence(path, node.lineno, value))

    return produced, consumed


def _compared_operands(node: ast.Compare | ast.MatchValue) -> list[ast.expr]:
    if isinstance(node, ast.MatchValue):
        return [node.value]
    if len(node.ops) != 1:
        return []
    if isinstance(node.ops[0], IDENTITY_NODES):
        return [node.left, *node.comparators]
    if isinstance(node.ops[0], MEMBERSHIP_NODES) and isinstance(
        node.comparators[0], CONTAINER_NODES
    ):
        return list(node.comparators[0].elts)

    return []


def _typescript_occurrences(
    path: str, source: str
) -> tuple[list[Occurrence], list[Occurrence]]:
    produced: list[Occurrence] = []
    consumed: list[Occurrence] = []

    for token, value in _message_tokens(source):
        before = _text_before(source, token)
        after = source[token.end() : token.end() + 20]
        line_number = source.count("\n", 0, token.start()) + 1
        occurrence = Occurrence(path, line_number, value)

        if _FIELD_BEFORE.search(before) or _CONSTRUCTOR_BEFORE.search(before):
            produced.append(occurrence)
        if (
            _COMPARISON_BEFORE.search(before)
            or _CASE_BEFORE.search(before)
            or _COMPARISON_AFTER.search(after)
        ):
            consumed.append(occurrence)

    return produced, consumed


def _message_tokens(source: str) -> list[MessageToken]:
    messages: list[MessageToken] = []
    constants: dict[str, str] = {}
    names: list[re.Match[str]] = []

    for token in _LEXICAL_TOKEN.finditer(source):
        if token.group().startswith(_COMMENT_START):
            continue
        if not token.group().startswith(_QUOTES):
            names.append(token)
            continue

        value = decoded_javascript_string(token.group())

        if value is None or not _is_human_message(value):
            continue

        declared = _CONSTANT_BEFORE.search(_text_before(source, token))

        if declared is not None:
            constants[declared.group(1)] = value

        messages.append((token, value))

    for name in names:
        if name.group() in constants:
            messages.append((name, constants[name.group()]))

    return messages


def _text_before(source: str, token: re.Match[str]) -> str:
    return source[max(0, token.start() - 100) : token.start()]


def reports_for(
    paths: list[str], consumer_suffixes: tuple[str, ...] = _SOURCE_SUFFIXES
) -> list[str]:
    produced: list[Occurrence] = []
    consumed: list[Occurrence] = []

    for path in paths:
        if path.endswith(_PYTHON_SUFFIXES):
            additions = _python_occurrences(path, parsed_module(path))
        elif path.endswith(_TYPESCRIPT_SUFFIXES):
            source = Path(path).read_text(encoding="utf-8", errors="replace")
            additions = _typescript_occurrences(path, source)
        else:
            continue

        produced.extend(additions[0])
        consumed.extend(additions[1])

    by_text: dict[str, list[Occurrence]] = {}

    for occurrence in produced:
        by_text.setdefault(occurrence.text, []).append(occurrence)

    reports: list[str] = []

    for consumer in sorted(set(consumed)):
        if not consumer.path.endswith(consumer_suffixes):
            continue

        producers = sorted(
            producer
            for producer in by_text.get(consumer.text, [])
            if producer.path != consumer.path
        )

        if not producers:
            continue

        producer = producers[0]
        reports.append(
            f"{consumer.path}:{consumer.line_number}: branches on human-readable "
            f"error text {json.dumps(consumer.text)} produced at "
            f"{producer.path}:{producer.line_number}; use a stable error code "
            "and handler registry"
        )

    return reports


def main() -> None:
    consumer_suffixes = (
        _CONSUMER_SUFFIXES[sys.argv[1]]
        if len(sys.argv) > 1
        else _SOURCE_SUFFIXES
    )

    for report in reports_for(paths_from_standard_input(), consumer_suffixes):
        _ = sys.stdout.write(f"{report}\n")


if __name__ == "__main__":
    main()
