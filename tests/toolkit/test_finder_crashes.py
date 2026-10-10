from pathlib import Path

import pytest

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
)

BROKEN_PYTHON = "def broken(:\n"
TERMS_PAST_THE_STACK = 5_000
NESTED_TYPESCRIPT = (
    "export function outer(): number {\n"
    "  function inner(): number {\n"
    "    return 1;\n"
    "  }\n"
    "  return inner();\n"
    "}\n"
)


def _deep_typescript() -> str:
    terms = " + ".join(["'a'"] * TERMS_PAST_THE_STACK)

    return f"export const joined = {terms};\n"


@pytest.mark.parametrize(
    ("check_name", "broken_path"),
    [
        ("nested-definitions", "user-service/src/broken.py"),
        ("dependency-inversion", "user-service/src/broken.py"),
        ("property-tests", "user-service/src/broken.py"),
        ("feature-isolation", "user-service/src/features/notes/broken.py"),
    ],
)
def test_a_crashing_python_finder_fails_its_check(
    tmp_path: Path, check_name: str, broken_path: str
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, broken_path, BROKEN_PYTHON)

    finished = run_check(tmp_path, check_name)

    assert finished.returncode != 0


def test_a_crashing_typescript_finder_fails_its_check(tmp_path: Path) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, "ui-service/src/nest.ts", NESTED_TYPESCRIPT)
    stage_file(tmp_path, "ui-service/src/deep.ts", _deep_typescript())

    finished = run_check(tmp_path, "nested-definitions")

    assert finished.returncode != 0
