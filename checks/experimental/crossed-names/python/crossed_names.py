import ast
import re
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple, cast

WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
COMPOUND = (
    ast.BinOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.UnaryOp,
    ast.Lambda,
)
STATEMENT_BLOCKS = ("body", "orelse", "finalbody")
BLOCK_HOLDERS = (ast.stmt, ast.Module, ast.excepthandler, ast.match_case)
SMALLEST_GROUP = 3
COMMON_VALUE_COUNT = 3
NAMED_SHARE_PARTS = 2
NAMED_SHARE_WHOLE = 3
SHOWN_LENGTH = 60
CUT_MARK = "..."

type Words = tuple[str, ...]
type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type Scope = ast.Module | FunctionNode


class Item(NamedTuple):
    key: str
    value: ast.expr
    line_number: int
    rebinds_key: bool


class Member(NamedTuple):
    item: Item
    key_words: Words
    value_words: frozenset[str]
    text: str
    is_compound: bool
    names_key: bool
    counts_as_named: bool


class Rename(NamedTuple):
    old: Words
    new: Words

    def apply(self, name: Words) -> Words | None:
        width = len(self.old)

        for start in range(len(name) - width + 1):
            if name[start : start + width] == self.old:
                return name[:start] + self.new + name[start + width :]

        return None


class CrossedName(NamedTuple):
    path: str
    line_number: int
    key: str
    source_key: str
    value: str


def words_of(name: str) -> Words:
    return tuple(match.group().lower() for match in WORD.finditer(name))


def expression_words(expression: ast.expr) -> frozenset[str]:
    found: set[str] = set()

    for node in ast.walk(expression):
        if isinstance(node, ast.Name):
            found.update(words_of(node.id))
        elif isinstance(node, ast.Attribute):
            found.update(words_of(node.attr))

    return frozenset(found)


def reads_name(expression: ast.expr, name: str) -> bool:
    return any(
        isinstance(node, ast.Name) and node.id == name
        for node in ast.walk(expression)
    )


def member_of(item: Item) -> Member:
    key_words = words_of(item.key)
    value_words = expression_words(item.value)
    names_key = set(key_words) <= value_words
    is_compound = any(
        isinstance(node, COMPOUND) for node in ast.walk(item.value)
    )

    return Member(
        item,
        key_words,
        value_words,
        ast.unparse(item.value),
        is_compound,
        names_key,
        names_key and not item.rebinds_key,
    )


def last_name(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return expression.attr

    return None


def is_alias(member: Member) -> bool:
    value = member.item.value
    callee = value.func if isinstance(value, ast.Call) else value
    name = last_name(callee)

    if name is None:
        return False

    return set(words_of(name)) == set(member.key_words)


def is_variant(removed: set[str], added: set[str]) -> bool:
    return any(
        old in new or new in old for old in removed for new in added
    )


def rename_between(member: Member, source: Member) -> Rename | None:
    own = set(member.key_words)
    other = set(source.key_words)
    removed = other - own
    added = own - other

    if not removed or not added or added & member.value_words:
        return None

    if is_variant(removed, added):
        return None

    old = tuple(word for word in source.key_words if word in removed)
    new = tuple(word for word in member.key_words if word in added)

    return Rename(old, new)


def assignment_parts(statement: ast.stmt) -> tuple[ast.expr, ast.expr] | None:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        return statement.targets[0], statement.value

    if isinstance(statement, ast.AnnAssign) and statement.value is not None:
        return statement.target, statement.value

    return None


def assigned_item(statement: ast.stmt) -> Item | None:
    parts = assignment_parts(statement)

    if parts is None:
        return None

    target, value = parts
    key = last_name(target)

    if key is None:
        return None

    rebinds = isinstance(target, ast.Name) and reads_name(value, key)

    return Item(key, value, statement.lineno, rebinds)


def assignment_runs(block: list[ast.stmt]) -> list[list[Item]]:
    runs: list[list[Item]] = [[]]

    for statement in block:
        item = assigned_item(statement)

        if item is None:
            runs.append([])
        else:
            runs[-1].append(item)

    return [run for run in runs if len(run) >= SMALLEST_GROUP]


def argument_item(key: str, value: ast.expr) -> Item:
    return Item(key, value, value.lineno, rebinds_key=False)


def identifier_key(key: ast.expr | None) -> str | None:
    if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
        return None

    return key.value if key.value.isidentifier() else None


def statement_blocks(node: ast.AST) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = []

    for field in STATEMENT_BLOCKS:
        block: object = getattr(node, field, None)

        if isinstance(block, list):
            blocks.append(cast("list[ast.stmt]", block))

    return blocks


def shortened(text: str) -> str:
    if len(text) <= SHOWN_LENGTH:
        return text

    return text[: SHOWN_LENGTH - len(CUT_MARK)] + CUT_MARK


class ScopeNames:
    def __init__(self, tree: ast.Module) -> None:
        self._tree: ast.Module = tree
        self._module_names: set[Words] | None = None
        self._by_scope: dict[Scope, set[Words]] = {}

    def has(self, scope: Scope, name: Words) -> bool:
        if scope not in self._by_scope:
            self._by_scope[scope] = self._local_names(scope)

        return name in self._by_scope[scope] or name in self._defined()

    def _defined(self) -> set[Words]:
        if self._module_names is None:
            self._module_names = self._definitions()

        return self._module_names

    def _definitions(self) -> set[Words]:
        names: set[Words] = set()

        for node in ast.walk(self._tree):
            if isinstance(node, ast.alias):
                bound = node.asname or node.name
                names.add(words_of(bound.rpartition(".")[2]))
            elif isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ):
                names.add(words_of(node.name))

        return names

    @staticmethod
    def _local_names(scope: Scope) -> set[Words]:
        names: set[Words] = set()

        for node in ast.walk(scope):
            if isinstance(node, ast.Name):
                names.add(words_of(node.id))
            elif isinstance(node, ast.arg):
                names.add(words_of(node.arg))

        return names


class Group:
    def __init__(self, scope: Scope, items: list[Item]) -> None:
        self._scope: Scope = scope
        self._members: list[Member] = [member_of(item) for item in items]
        named = [m.item.key for m in self._members if m.counts_as_named]
        self._named_count: int = len(named)
        self._named_by_key: Counter[str] = Counter(named)
        self._key_counts: Counter[str] = Counter(
            member.item.key for member in self._members
        )
        self._by_text: dict[str, list[Member]] = {}

        for member in self._members:
            self._by_text.setdefault(member.text, []).append(member)

    def crossed(self, names: ScopeNames) -> list[tuple[Member, Member]]:
        found: list[tuple[Member, Member]] = []

        for member in self._members:
            if not self._is_suspect(member):
                continue

            source = self._source_of(member, names)

            if source is not None:
                found.append((member, source))

        return found

    def _is_suspect(self, member: Member) -> bool:
        if member.is_compound or member.names_key:
            return False

        if len(self._by_text[member.text]) >= COMMON_VALUE_COUNT:
            return False

        key = member.item.key
        others = len(self._members) - self._key_counts[key]
        named_others = self._named_count - self._named_by_key[key]

        return (
            NAMED_SHARE_WHOLE * named_others >= NAMED_SHARE_PARTS * others
        )

    def _source_of(self, member: Member, names: ScopeNames) -> Member | None:
        for source in self._by_text[member.text]:
            if source.item.key == member.item.key:
                continue

            if not source.counts_as_named or is_alias(source):
                continue

            rename = rename_between(member, source)

            if rename is None:
                continue

            if self._points_elsewhere(member.item.value, rename, names):
                return source

        return None

    def _points_elsewhere(
        self, value: ast.expr, rename: Rename, names: ScopeNames
    ) -> bool:
        renamed_names: list[Words] = []

        for node in ast.walk(value):
            if isinstance(node, ast.Attribute):
                if rename.apply(words_of(node.attr)) is not None:
                    return True
            elif isinstance(node, ast.Name):
                renamed = rename.apply(words_of(node.id))

                if renamed is not None:
                    renamed_names.append(renamed)

        if not renamed_names:
            return True

        return any(names.has(self._scope, name) for name in renamed_names)


def scoped_nodes(tree: ast.Module) -> list[tuple[ast.AST, Scope]]:
    found: list[tuple[ast.AST, Scope]] = []
    pending: list[tuple[ast.AST, Scope]] = [(tree, tree)]

    while pending:
        node, scope = pending.pop()
        found.append((node, scope))

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            scope = node

        for child in ast.iter_child_nodes(node):
            pending.append((child, scope))

    return found


def keyword_items(call: ast.Call) -> list[Item]:
    items: list[Item] = []

    for keyword in call.keywords:
        if keyword.arg is not None:
            items.append(argument_item(keyword.arg, keyword.value))

    return items


def entry_items(dictionary: ast.Dict) -> list[Item]:
    items: list[Item] = []

    for key, value in zip(dictionary.keys, dictionary.values, strict=True):
        name = identifier_key(key)

        if name is not None:
            items.append(argument_item(name, value))

    return items


def statement_runs(node: ast.AST) -> list[list[Item]]:
    runs: list[list[Item]] = []

    for block in statement_blocks(node):
        runs.extend(assignment_runs(block))

    return runs


def item_groups(node: ast.AST) -> list[list[Item]]:
    if isinstance(node, ast.Call):
        groups = [keyword_items(node)]
    elif isinstance(node, ast.Dict):
        groups = [entry_items(node)]
    elif isinstance(node, BLOCK_HOLDERS):
        groups = statement_runs(node)
    else:
        groups = []

    return [group for group in groups if len(group) >= SMALLEST_GROUP]


def groups_in(tree: ast.Module) -> list[Group]:
    groups: list[Group] = []

    for node, scope in scoped_nodes(tree):
        for items in item_groups(node):
            groups.append(Group(scope, items))

    return groups


class CrossedNames:
    def find_in(self, paths: list[str]) -> list[CrossedName]:
        found: dict[tuple[str, int], CrossedName] = {}

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for crossed in self._crossed_in(path, tree):
                location = (crossed.path, crossed.line_number)
                _ = found.setdefault(location, crossed)

        return sorted(found.values())

    @staticmethod
    def _crossed_in(path: str, tree: ast.Module) -> list[CrossedName]:
        names = ScopeNames(tree)
        crossed: list[CrossedName] = []

        for group in groups_in(tree):
            for member, source in group.crossed(names):
                crossed.append(
                    CrossedName(
                        path,
                        member.item.line_number,
                        member.item.key,
                        source.item.key,
                        shortened(member.text),
                    )
                )

        return crossed


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for crossed_name in CrossedNames().find_in(source_paths):
    location = f"{crossed_name.path}:{crossed_name.line_number}"
    key = crossed_name.key
    copied = f"{key} takes the value written for {crossed_name.source_key}"
    value = f"({crossed_name.value})"
    fix = f"give {key} its own value"
    _ = sys.stdout.write(f"{location}: {copied} {value} - {fix}\n")
