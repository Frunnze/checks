import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from module_constants import string_constants
from python_structure_types import parsed_module
from standard_input import paths_from_standard_input

_ERROR_FIELDS = {"content", "detail", "error", "message", "reason"}
_ERROR_CONSTRUCTORS = ("Error", "Exception", "Response")
_COMMENT_START = "/"
_LEXICAL_TOKEN = re.compile(
    r"//[^\n]*|/\*.*?\*/"
    r'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`',
    re.DOTALL,
)
_ESCAPE = re.compile(
    r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\r\n|.)",
    re.DOTALL,
)
_CODE_POINT_ESCAPES = ("u", "x")
_CHARACTER_ESCAPES = {
    "0": "\0",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\n": "",
    "\r": "",
    "\r\n": "",
    "\u2028": "",
    "\u2029": "",
}
_COMPARISON_BEFORE = re.compile(r"(?:===|!==|==|!=)\s*$")
_COMPARISON_AFTER = re.compile(r"^\s*(?:===|!==|==|!=)")
_FIELD_BEFORE = re.compile(
    r"(?:content|detail|error|message|reason)\s*:\s*$"
)
_CONSTRUCTOR_BEFORE = re.compile(
    r"new\s+(?:[A-Za-z_$][\w$]*)?(?:Error|Exception|Response)\s*\(\s*$"
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


def _unescaped(escape: re.Match[str]) -> str:
    sequence = escape.group(1)

    if len(sequence) > 1 and sequence.startswith(_CODE_POINT_ESCAPES):
        code_point = int(sequence[1:].strip("{}"), 16)

        if code_point > sys.maxunicode:
            return escape.group()

        return chr(code_point)

    return _CHARACTER_ESCAPES.get(sequence, sequence)


def _decoded_javascript_string(written: str) -> str | None:
    body = written[1:-1]

    if written.startswith("`") and "${" in body:
        return None

    code_units = _ESCAPE.sub(_unescaped, body).encode(
        "utf-16-le", "surrogatepass"
    )

    return code_units.decode("utf-16-le", "surrogatepass")


def _typescript_occurrences(
    path: str, source: str
) -> tuple[list[Occurrence], list[Occurrence]]:
    produced: list[Occurrence] = []
    consumed: list[Occurrence] = []

    for match in _LEXICAL_TOKEN.finditer(source):
        if match.group().startswith(_COMMENT_START):
            continue

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
        if path.endswith(".py"):
            additions = _python_occurrences(path, parsed_module(path))
        elif path.endswith((".ts", ".tsx", ".mts", ".cts")):
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
    for report in reports_for(paths_from_standard_input()):
        _ = sys.stdout.write(f"{report}\n")


if __name__ == "__main__":
    main()
