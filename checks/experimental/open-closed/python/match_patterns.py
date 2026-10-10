import ast


def subject_patterns(pattern: ast.pattern) -> list[ast.pattern]:
    if isinstance(pattern, ast.MatchOr):
        found: list[ast.pattern] = []

        for alternative in pattern.patterns:
            found.extend(subject_patterns(alternative))

        return found
    if isinstance(pattern, ast.MatchAs) and pattern.pattern is not None:
        return subject_patterns(pattern.pattern)

    return [pattern]
