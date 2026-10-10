import ast
import re
from collections import defaultdict

from ocp_findings import ScatteredVariantDispatch
from string_comparisons import StringComparisons

Scope = ast.FunctionDef | ast.AsyncFunctionDef
OwnedScope = tuple[str, Scope]

_ROOT_NAME = re.compile(r"\w+")
_INSTANCE_NAMES = {"self", "cls"}
_MODULE_OWNER = ""


def top_level_scopes(tree: ast.Module) -> list[OwnedScope]:
    found: list[OwnedScope] = []

    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((_MODULE_OWNER, statement))
        elif isinstance(statement, ast.ClassDef):
            found.extend(
                (statement.name, member)
                for member in statement.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            )

    return found


def scattered_comparisons(
    path: str,
    scopes: list[OwnedScope],
    constants: dict[str, str],
) -> list[ScatteredVariantDispatch]:
    grouped: dict[
        str, list[tuple[Scope, str, str, tuple[str, ...]]]
    ] = defaultdict(list)

    for owner, scope in scopes:
        collector = StringComparisons(scope, constants)
        collector.visit(scope)

        for key, subject, variants in collector.with_at_least(1):
            site_key = _site_key(owner, key, subject)
            grouped[site_key].append((scope, scope.name, subject, variants))

    found: list[ScatteredVariantDispatch] = []

    for sites in grouped.values():
        variants = tuple(sorted({value for *_, values in sites for value in values}))

        if len(sites) < 2 or len(variants) < 2:
            continue

        first_scope, first_name, subject, _ = min(
            sites, key=lambda site: site[0].lineno
        )
        found.append(
            ScatteredVariantDispatch(
                path,
                first_scope.lineno,
                first_name,
                subject,
                variants,
                len(sites),
            )
        )

    return sorted(found)


def _site_key(owner: str, key: str, subject: str) -> str:
    root = _ROOT_NAME.match(subject)

    if root is None or root.group() not in _INSTANCE_NAMES:
        return key

    return f"{owner}.{key}"
