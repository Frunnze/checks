import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from module_constants import string_constants

_ERROR_FIELDS = {"content", "detail", "error", "message", "reason"}
_ERROR_CONSTRUCTORS = ("Error", "Exception", "Response")
_QUOTED = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`'
)
_COMPARISON_BEFORE = re.compile(r"(?:===|!==|==|!=)\s*$")
_COMPARISON_AFTER = re.compile(r"^\s*(?:===|!==|==|!=)")
_FIELD_BEFORE = re.compile(
    r"(?:content|detail|error|message|reason)\s*:\s*$"
)
_CONSTRUCTOR_BEFORE = re.compile(
    r"new\s+[A-Za-z_$][\w$]*(?:Error|Exception|Response)\s*\(\s*$"
)


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

        if (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], (ast.Eq, ast.NotEq, ast.Is, ast.IsNot))
        ):
            values = [
                _constant_value(node.left, constants),
                *(
                    _constant_value(comparator, constants)
                    for comparator in node.comparators
                ),
            ]

            for value in values:
                if value is not None and _is_human_message(value):
                    consumed.append(Occurrence(path, node.lineno, value))

    return produced, consumed


def _decoded_javascript_string(written: str) -> str | None:
    if written.startswith("`"):
        body = written[1:-1]

        return None if "${" in body else bytes(body, "utf-8").decode("unicode_escape")

    try:
        if written.startswith('"'):
            decoded: object = json.loads(written)
        else:
            decoded = ast.literal_eval(written)
    except (ValueError, SyntaxError, json.JSONDecodeError):
        return None

    return decoded if isinstance(decoded, str) else None


def _typescript_occurrences(
    path: str, source: str
) -> tuple[list[Occurrence], list[Occurrence]]:
    produced: list[Occurrence] = []
    consumed: list[Occurrence] = []

    for match in _QUOTED.finditer(source):
        value = _decoded_javascript_string(match.group())

        if value is None or not _is_human_message(value):
            continue

        before = source[max(0, match.start() - 100) : match.start()]
        after = source[match.end() : match.end() + 20]
        line_number = source.count("\n", 0, match.start()) + 1
        occurrence = Occurrence(path, line_number, value)

        if _FIELD_BEFORE.search(before) or _CONSTRUCTOR_BEFORE.search(before):
            produced.append(occurrence)
        if _COMPARISON_BEFORE.search(before) or _COMPARISON_AFTER.search(after):
            consumed.append(occurrence)

    return produced, consumed


def reports_for(paths: list[str]) -> list[str]:
    produced: list[Occurrence] = []
    consumed: list[Occurrence] = []

    for path in paths:
        source = Path(path).read_text(encoding="utf-8")

        if path.endswith(".py"):
            additions = _python_occurrences(path, ast.parse(source))
        elif path.endswith((".ts", ".tsx")):
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
    for report in reports_for(sys.stdin.read().split()):
        _ = sys.stdout.write(f"{report}\n")


if __name__ == "__main__":
    main()
