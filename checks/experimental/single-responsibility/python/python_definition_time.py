import ast
from collections.abc import Iterator

from python_bindings import SCOPES
from python_metrics import RuntimeMetrics
from srp_metrics import CallableFacts


def direct_scopes(node: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, SCOPES):
            yield child
        else:
            yield from direct_scopes(child)


def definition_defaults(node: ast.AST) -> list[ast.expr]:
    defaults: list[ast.expr] = []
    for scope in direct_scopes(node):
        if isinstance(scope, ast.ClassDef):
            continue
        defaults.extend(scope.args.defaults)
        for keyword_default in scope.args.kw_defaults:
            if keyword_default is not None:
                defaults.append(keyword_default)
    return defaults


def collect_definition_body(
    collector: RuntimeMetrics, node: ast.Module | ast.ClassDef
) -> CallableFacts:
    for statement in node.body:
        collector.statement(statement)
    for default in definition_defaults(node):
        collector.visit(default)
    return collector.finish()
