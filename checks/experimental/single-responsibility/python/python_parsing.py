import ast
from pathlib import Path

UNKNOWN_LINE = 1


def parse_python_module(path: Path) -> ast.Module:
    source_bytes = path.read_bytes()
    try:
        return ast.parse(source_bytes, filename=str(path))
    except SyntaxError as error:
        line = error.lineno or UNKNOWN_LINE
        location = (str(path), line, error.offset, error.text)
        raise SyntaxError(error.msg, location) from error
