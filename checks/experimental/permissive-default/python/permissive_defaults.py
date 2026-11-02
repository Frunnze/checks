import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

ENVIRONMENT_READERS = frozenset(
    {"os.getenv", "getenv", "os.environ.get", "environ.get"}
)
OPENING_WORDS = frozenset({"debug", "insecure", "unsafe"})
PROTECTING_WORDS = frozenset(
    {"verify", "secure", "auth", "authentication", "csrf", "https", "tls"}
)
WILDCARD_WORDS = frozenset({"origins", "hosts", "cors"})
SECRET_WORDS = frozenset({"secret", "password", "passwd", "token", "key"})
NOT_SECRET_WORDS = frozenset(
    {"name", "path", "file", "url", "header", "id", "prefix", "type", "env"}
)
ON_VALUES = frozenset({"1", "true", "yes", "on"})
OFF_VALUES = frozenset({"0", "false", "no", "off"})
WILDCARD = "*"
NAME_AND_DEFAULT = 2
WORD_BOUNDARY = re.compile(r"[^a-zA-Z0-9]+|(?<=[a-z0-9])(?=[A-Z])")


class PermissiveDefault(NamedTuple):
    path: str
    line_number: int
    setting: str
    default: str
    reason: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return f"{owner}.{expression.attr}" if owner else ""

    return ""


def text_of(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Constant):
        value = expression.value

        if isinstance(value, bool):
            return str(value).lower()

        if isinstance(value, str | int):
            return str(value)

    return None


def words_of(name: str) -> set[str]:
    return {word.lower() for word in WORD_BOUNDARY.split(name) if word}


def risk_of(setting: str, default: str) -> str | None:
    words = words_of(setting)
    value = default.strip().lower()

    if words & OPENING_WORDS and value in ON_VALUES:
        return "it switches the unsafe mode on"

    if words & PROTECTING_WORDS and value in OFF_VALUES:
        return "it switches the protection off"

    if words & WILDCARD_WORDS and value == WILDCARD:
        return "it allows every origin"

    is_secret = bool(words & SECRET_WORDS) and not (words & NOT_SECRET_WORDS)

    if is_secret and value and value not in ON_VALUES | OFF_VALUES:
        return "every deployment shares this secret"

    return None


class PermissiveDefaults:
    def find_in(self, paths: list[str]) -> list[PermissiveDefault]:
        found: list[PermissiveDefault] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    finding = self._in_call(path, node)

                    if finding is not None:
                        found.append(finding)

        return sorted(found)

    def _in_call(self, path: str, call: ast.Call) -> PermissiveDefault | None:
        if dotted_name(call.func) not in ENVIRONMENT_READERS:
            return None

        if len(call.args) != NAME_AND_DEFAULT:
            return None

        setting = text_of(call.args[0])
        default = text_of(call.args[1])

        if setting is None or default is None:
            return None

        reason = risk_of(setting, default)

        if reason is None:
            return None

        return PermissiveDefault(path, call.lineno, setting, default, reason)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for default in PermissiveDefaults().find_in(source_paths):
    location = f"{default.path}:{default.line_number}"
    problem = f"{default.setting} falls back to {default.default!r} when unset"
    _ = sys.stdout.write(f"{location}: {problem} - {default.reason}\n")
