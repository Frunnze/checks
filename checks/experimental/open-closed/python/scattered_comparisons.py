import ast
from collections import defaultdict

from ocp_findings import ScatteredVariantDispatch
from string_comparisons import StringComparisons

Scope = ast.FunctionDef | ast.AsyncFunctionDef


def top_level_scopes(tree: ast.Module) -> list[Scope]:
    found: list[Scope] = []

    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(statement)
        elif isinstance(statement, ast.ClassDef):
            found.extend(
                member
                for member in statement.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            )

    return found


def scattered_comparisons(
    path: str,
    scopes: list[Scope],
    constants: dict[str, str],
) -> list[ScatteredVariantDispatch]:
    grouped: dict[
        str, list[tuple[Scope, str, str, tuple[str, ...]]]
    ] = defaultdict(list)

    for scope in scopes:
        collector = StringComparisons(scope, constants)
        collector.visit(scope)

        for key, subject, variants in collector.with_at_least(1):
            grouped[key].append((scope, scope.name, subject, variants))

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
