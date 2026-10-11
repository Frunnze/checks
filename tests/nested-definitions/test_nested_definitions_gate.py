from pathlib import Path

import pytest

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
)

NESTED_TESTS = [
    (
        "user-service",
        "app.py",
        "ONE = 1\n",
        "test_nested.py",
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner()\n",
    ),
    (
        "ui-service",
        "app.ts",
        "export const one = 1;\n",
        "nested.test.ts",
        "export function outer(): number {\n"
        "  function inner(): number { return 1; }\n"
        "  return inner();\n"
        "}\n",
    ),
]


@pytest.mark.parametrize(
    "service, source_name, source, test_name, test_source", NESTED_TESTS
)
def test_reads_the_tests_beside_a_source_folder(
    tmp_path: Path,
    service: str,
    source_name: str,
    source: str,
    test_name: str,
    test_source: str,
) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, f"{service}/src/{source_name}", source)
    stage_file(tmp_path, f"{service}/tests/{test_name}", test_source)

    finished = run_check(tmp_path, "nested-definitions")

    assert finished.returncode == 1
    assert f"{service}/tests/{test_name}:2: inner" in finished.stderr
