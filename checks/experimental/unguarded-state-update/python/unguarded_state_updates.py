import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple, TypeGuard

STATE_WORDS = frozenset({"status", "state", "phase", "stage", "step"})
SQL_TOKEN_PATTERNS = (
    r"--[^\n]*",
    r"/\*.*?\*/",
    r"'(?:[^']|'')*'",
    r'"(?:[^"]|"")*"',
    r"(?<!:):[A-Za-z_]\w*",
    r"%\(\w+\)s",
    r"[@$]\w+",
    r"[A-Za-z_][A-Za-z0-9_$]*",
    r"\S",
)
SQL_TOKEN = re.compile("|".join(SQL_TOKEN_PATTERNS), re.DOTALL)
COMMENT_STARTS = ("--", "/*")
IDENTIFIER_QUOTE = '"'
UNKNOWN_START = "{"
UNKNOWN_END = "}"
UNKNOWN_TEXT = UNKNOWN_START + UNKNOWN_END
UPDATE = "update"
SET = "set"
WHERE = "where"
SET_ENDS = frozenset({"from", "where", "returning"})
WHERE_ENDS = frozenset({"returning"})
NOT_A_STATEMENT_AFTER = frozenset({"do", "for"})
STATEMENT_END = ";"
OPENING = "("
CLOSING = ")"
COMMA = ","
EQUALS = "="
DOT = "."
WORD_SEPARATOR = "_"
TABLE_PUNCTUATION = frozenset({DOT, UNKNOWN_START, UNKNOWN_END})
MAX_TABLE_TOKENS = 6


class SqlToken(NamedTuple):
    text: str
    depth: int
    is_word: bool


class Assignment(NamedTuple):
    columns: list[str]
    value_words: set[str]


class UpdateStatement(NamedTuple):
    assignments: list[Assignment]
    where_words: set[str]
    where_is_known: bool


class UnguardedUpdate(NamedTuple):
    path: str
    line_number: int
    column: str


def sql_tokens(text: str) -> list[SqlToken]:
    tokens: list[SqlToken] = []
    depth = 0

    for match in SQL_TOKEN.finditer(text):
        token = match.group()

        if token.startswith(COMMENT_STARTS):
            continue

        if token == CLOSING:
            depth -= 1

        tokens.append(word_token(token, depth))

        if token == OPENING:
            depth += 1

    return tokens


def word_token(token: str, depth: int) -> SqlToken:
    if token.startswith(IDENTIFIER_QUOTE):
        name = token.strip(IDENTIFIER_QUOTE).lower()
        return SqlToken(name, depth, is_word=True)

    is_word = token[0].isalpha() or token[0] == WORD_SEPARATOR
    return SqlToken(token.lower(), depth, is_word=is_word)


def is_table_token(token: SqlToken) -> bool:
    return token.is_word or token.text in TABLE_PUNCTUATION


def set_keyword_after(
    tokens: list[SqlToken], update_index: int
) -> int | None:
    depth = tokens[update_index].depth
    first = update_index + 1

    for offset, token in enumerate(tokens[first:]):
        if token.depth == depth and token.text == SET:
            return first + offset

        if offset >= MAX_TABLE_TOKENS or not is_table_token(token):
            return None

    return None


def clause(
    tokens: list[SqlToken], start: int, ends: frozenset[str]
) -> list[SqlToken]:
    depth = tokens[start].depth
    found: list[SqlToken] = []

    for token in tokens[start + 1:]:
        if token.depth < depth:
            break

        if token.depth == depth and token.text in ends | {STATEMENT_END}:
            break

        found.append(token)

    return found


def where_after(tokens: list[SqlToken], set_index: int) -> int | None:
    depth = tokens[set_index].depth

    for index in range(set_index + 1, len(tokens)):
        token = tokens[index]

        if token.depth < depth or token.text == STATEMENT_END:
            return None

        if token.depth == depth and token.text == WHERE:
            return index

    return None


def split_at_depth(
    tokens: list[SqlToken], separator: str, depth: int
) -> list[list[SqlToken]]:
    parts: list[list[SqlToken]] = [[]]

    for token in tokens:
        if token.depth == depth and token.text == separator:
            parts.append([])
        else:
            parts[-1].append(token)

    return parts


def column_names(target: list[SqlToken]) -> list[str]:
    names: list[str] = []

    for index, token in enumerate(target):
        following = target[index + 1] if index + 1 < len(target) else None

        if not token.is_word:
            continue

        if following is None or following.text != DOT:
            names.append(token.text)

    return names


def words_of(tokens: list[SqlToken]) -> set[str]:
    return {token.text for token in tokens if token.is_word}


def assignments_in(set_tokens: list[SqlToken]) -> list[Assignment]:
    if not set_tokens:
        return []

    depth = set_tokens[0].depth
    found: list[Assignment] = []

    for part in split_at_depth(set_tokens, COMMA, depth):
        target, *value_sides = split_at_depth(part, EQUALS, depth)

        if not value_sides:
            continue

        value = [token for side in value_sides for token in side]
        found.append(Assignment(column_names(target), words_of(value)))

    return found


def update_at(tokens: list[SqlToken], index: int) -> UpdateStatement | None:
    if tokens[index].text != UPDATE:
        return None

    if index > 0 and tokens[index - 1].text in NOT_A_STATEMENT_AFTER:
        return None

    set_index = set_keyword_after(tokens, index)

    if set_index is None:
        return None

    set_tokens = clause(tokens, set_index, SET_ENDS)
    where_index = where_after(tokens, set_index)

    if where_index is None:
        return None

    where_tokens = clause(tokens, where_index, WHERE_ENDS)
    where_texts = {token.text for token in where_tokens}

    return UpdateStatement(
        assignments_in(set_tokens),
        words_of(where_tokens),
        UNKNOWN_START not in where_texts,
    )


def update_statements(text: str) -> list[UpdateStatement]:
    if UPDATE not in text.lower():
        return []

    tokens = sql_tokens(text)
    statements: list[UpdateStatement] = []

    for index in range(len(tokens)):
        statement = update_at(tokens, index)

        if statement is not None:
            statements.append(statement)

    return statements


def is_state_column(column: str) -> bool:
    return column.rpartition(WORD_SEPARATOR)[2] in STATE_WORDS


def versioned_columns(statement: UpdateStatement) -> set[str]:
    found: set[str] = set()

    for assignment in statement.assignments:
        for column in assignment.columns:
            if column in assignment.value_words:
                found.add(column)

    return found


def unguarded_columns(statement: UpdateStatement) -> list[str]:
    if not statement.where_is_known:
        return []

    if versioned_columns(statement) & statement.where_words:
        return []

    found: list[str] = []

    for assignment in statement.assignments:
        for column in assignment.columns:
            if not is_state_column(column):
                continue

            if column in assignment.value_words:
                continue

            if column not in statement.where_words:
                found.append(column)

    return found


def is_concatenation(expression: ast.expr) -> TypeGuard[ast.BinOp]:
    return isinstance(expression, ast.BinOp) and isinstance(
        expression.op, ast.Add
    )


def concatenated_parts(expression: ast.expr) -> list[ast.expr]:
    parts: list[ast.expr] = []
    remaining = expression

    while is_concatenation(remaining):
        parts.append(remaining.right)
        remaining = remaining.left

    parts.append(remaining)
    parts.reverse()
    return parts


def is_literal_text(expression: ast.expr) -> bool:
    if isinstance(expression, ast.Constant):
        return isinstance(expression.value, str)

    return isinstance(expression, ast.JoinedStr)


def is_text(expression: ast.expr) -> bool:
    if is_concatenation(expression):
        return any(is_text(part) for part in concatenated_parts(expression))

    return is_literal_text(expression)


def rendered(expression: ast.expr) -> str:
    if isinstance(expression, ast.Constant) and isinstance(
        expression.value, str
    ):
        return expression.value

    if isinstance(expression, ast.JoinedStr):
        return "".join(rendered(part) for part in expression.values)

    if is_concatenation(expression):
        parts = concatenated_parts(expression)
        return "".join(rendered(part) for part in parts)

    return UNKNOWN_TEXT


def texts_in(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    pending: list[ast.AST] = [tree]

    while pending:
        node = pending.pop()

        if isinstance(node, ast.Expr) and is_text(node.value):
            continue

        if isinstance(node, ast.expr) and is_text(node):
            found.append((node.lineno, rendered(node)))
        else:
            pending.extend(ast.iter_child_nodes(node))

    return found


class UnguardedStateUpdates:
    def find_in(self, paths: list[str]) -> list[UnguardedUpdate]:
        found: set[UnguardedUpdate] = set()

        for path in paths:
            found.update(self._find_in_file(path))

        return sorted(found)

    def _find_in_file(self, path: str) -> list[UnguardedUpdate]:
        tree = ast.parse(Path(path).read_bytes(), path)
        found: list[UnguardedUpdate] = []

        for line_number, text in texts_in(tree):
            for statement in update_statements(text):
                for column in unguarded_columns(statement):
                    found.append(UnguardedUpdate(path, line_number, column))

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for update in UnguardedStateUpdates().find_in(source_paths):
    location = f"{update.path}:{update.line_number}"
    problem = (
        f"UPDATE sets {update.column} but its WHERE does not test"
        f" {update.column}, so it overwrites a concurrent change"
    )
    fix = (
        f"add AND {update.column} = <the state you read> to the WHERE"
        " and check the row count"
    )
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
