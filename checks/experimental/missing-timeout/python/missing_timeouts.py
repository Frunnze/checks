import ast
import sys
from pathlib import Path
from typing import NamedTuple


class TimeoutRule(NamedTuple):
    option: str
    position: int | None
    address: str | None
    address_may_carry: bool
    excuses: frozenset[str]


class MissingTimeout(NamedTuple):
    path: str
    line_number: int
    client: str
    option: str


STANDARD_TIMEOUT = "timeout"
STANDARD_POSITIONS = {
    "urllib.request.urlopen": 2,
    "socket.create_connection": 1,
    "http.client.HTTPConnection": 2,
    "http.client.HTTPSConnection": 4,
    "smtplib.SMTP": 3,
    "smtplib.SMTP_SSL": 5,
    "smtplib.LMTP": 4,
    "ftplib.FTP": 4,
    "ftplib.FTP_TLS": 7,
    "poplib.POP3": 2,
    "poplib.POP3_SSL": 4,
    "imaplib.IMAP4": 2,
    "imaplib.IMAP4_SSL": 5,
}
REDIS_TIMEOUT = "socket_timeout"
REDIS_TIMEOUT_POSITION = 4
REDIS_URL = "url"
REDIS_POOL = frozenset({"connection_pool"})
REDIS_MODULES = (
    "redis",
    "redis.client",
    "redis.connection",
    "redis.cluster",
    "redis.asyncio",
    "redis.asyncio.client",
    "redis.asyncio.connection",
    "redis.asyncio.cluster",
)
REDIS_CLIENTS = ("Redis", "StrictRedis")
REDIS_BUILDERS = ("RedisCluster", "ConnectionPool", "BlockingConnectionPool")
URL_BUILDER = "from_url"
POSTGRES_CONNECT = "psycopg2.connect"
POSTGRES_TIMEOUT = "connect_timeout"
POSTGRES_ADDRESS = "dsn"
NO_EXCUSES: frozenset[str] = frozenset()


def redis_rule(position: int | None, address: str | None) -> TimeoutRule:
    return TimeoutRule(
        option=REDIS_TIMEOUT,
        position=position,
        address=address,
        address_may_carry=False,
        excuses=REDIS_POOL,
    )


def redis_rules() -> dict[str, TimeoutRule]:
    client = redis_rule(REDIS_TIMEOUT_POSITION, None)
    builder = redis_rule(None, None)
    from_url = redis_rule(None, REDIS_URL)
    rules: dict[str, TimeoutRule] = {}

    for module in REDIS_MODULES:
        rules[f"{module}.{URL_BUILDER}"] = from_url

        for name in REDIS_CLIENTS + REDIS_BUILDERS:
            rules[f"{module}.{name}"] = (
                client if name in REDIS_CLIENTS else builder
            )
            rules[f"{module}.{name}.{URL_BUILDER}"] = from_url

    return rules


def timeout_rules() -> dict[str, TimeoutRule]:
    rules = redis_rules()

    for name, position in STANDARD_POSITIONS.items():
        rules[name] = TimeoutRule(
            option=STANDARD_TIMEOUT,
            position=position,
            address=None,
            address_may_carry=False,
            excuses=NO_EXCUSES,
        )

    rules[POSTGRES_CONNECT] = TimeoutRule(
        option=POSTGRES_TIMEOUT,
        position=None,
        address=POSTGRES_ADDRESS,
        address_may_carry=True,
        excuses=NO_EXCUSES,
    )
    return rules


TIMEOUT_RULES = timeout_rules()


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        receiver = dotted_name(expression.value)
        return f"{receiver}.{expression.attr}" if receiver else ""

    return ""


def import_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is None:
                    root = alias.name.partition(".")[0]
                    aliases[root] = root
                else:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                bound = alias.asname or alias.name
                aliases[bound] = f"{node.module}.{alias.name}"

    return aliases


def qualified_name(call: ast.Call, aliases: dict[str, str]) -> str | None:
    root, dot, rest = dotted_name(call.func).partition(".")

    if root not in aliases:
        return None

    return f"{aliases[root]}{dot}{rest}"


def address_argument(call: ast.Call, keyword_name: str) -> ast.expr | None:
    if call.args:
        return call.args[0]

    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return keyword.value

    return None


def literal_text(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Constant) and isinstance(
        expression.value, str
    ):
        return expression.value

    return None


def address_carries(call: ast.Call, rule: TimeoutRule) -> bool:
    if rule.address is None:
        return False

    address = address_argument(call, rule.address)

    if address is None:
        return False

    text = literal_text(address)

    if text is None:
        return rule.address_may_carry

    return rule.option in text


def passes_unknown_arguments(call: ast.Call) -> bool:
    for argument in call.args:
        if isinstance(argument, ast.Starred):
            return True

    return any(keyword.arg is None for keyword in call.keywords)


def lacks_timeout(call: ast.Call, rule: TimeoutRule) -> bool:
    if passes_unknown_arguments(call):
        return False

    for keyword in call.keywords:
        if keyword.arg == rule.option or keyword.arg in rule.excuses:
            return False

    if rule.position is not None and len(call.args) > rule.position:
        return False

    return not address_carries(call, rule)


class MissingTimeouts:
    def find_in(self, paths: list[str]) -> list[MissingTimeout]:
        found: set[MissingTimeout] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            found.update(self._find_in_tree(path, tree))

        return sorted(found)

    def _find_in_tree(
        self, path: str, tree: ast.Module
    ) -> list[MissingTimeout]:
        aliases = import_aliases(tree)
        found: list[MissingTimeout] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            client = qualified_name(node, aliases)

            if client is None or client not in TIMEOUT_RULES:
                continue

            rule = TIMEOUT_RULES[client]

            if lacks_timeout(node, rule):
                found.append(
                    MissingTimeout(path, node.lineno, client, rule.option)
                )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for missing in MissingTimeouts().find_in(source_paths):
    location = f"{missing.path}:{missing.line_number}"
    problem = (
        f"{missing.client}() has no {missing.option}, so a stalled peer"
        " blocks it forever"
    )
    fix = f"pass {missing.option}="
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
