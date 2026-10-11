from pathlib import Path

import pytest

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_configured,
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


def _nested_tests_run(
    tmp_path: Path,
    service: str,
    files: tuple[str, str, str, str],
    listed_folders: list[str],
) -> str:
    source_name, source, test_name, test_source = files
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, f"{service}/src/{source_name}", source)
    stage_file(tmp_path, f"{service}/tests/{test_name}", test_source)
    listed = ", ".join(f'"{service}/{folder}"' for folder in listed_folders)
    configuration = (
        f"source_directories = [{listed}]\n"
        '[checks.nested-definitions]\nwhen = "pre-commit"\n'
    )

    finished = run_configured(tmp_path, configuration, "nested-definitions")

    return finished.stderr


@pytest.mark.parametrize(
    "service, source_name, source, test_name, test_source", NESTED_TESTS
)
def test_skips_a_tests_folder_that_is_not_a_source_folder(
    tmp_path: Path,
    service: str,
    source_name: str,
    source: str,
    test_name: str,
    test_source: str,
) -> None:
    files = (source_name, source, test_name, test_source)

    stderr = _nested_tests_run(tmp_path, service, files, ["src"])

    assert f"{service}/tests/{test_name}" not in stderr


@pytest.mark.parametrize(
    "service, source_name, source, test_name, test_source", NESTED_TESTS
)
def test_reads_a_tests_folder_listed_as_a_source_folder(
    tmp_path: Path,
    service: str,
    source_name: str,
    source: str,
    test_name: str,
    test_source: str,
) -> None:
    files = (source_name, source, test_name, test_source)

    stderr = _nested_tests_run(tmp_path, service, files, ["src", "tests"])

    assert f"{service}/tests/{test_name}:2: inner" in stderr
