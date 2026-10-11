from pathlib import Path

import pytest

from check_support import (
    link_toolkit_tool,
    repository,
    run_configured,
    stage_file,
)


RUFF_TABLES = [
    (
        "[checks.linters.ruff.lint]\n"
        'select = ["E", "F"]\n'
        'ignore = ["E501"]\n',
        f'VALUE = "{"x" * 90}"\n',
        0,
        0,
    ),
    (
        "[checks.linters.ruff.lint.flake8-tidy-imports.banned-api]\n"
        '"json".msg = "use the client"\n'
        '"pickle".msg = "use the client"\n',
        "import json\nimport pickle\n\nVALUES = (json, pickle)\n",
        1,
        2,
    ),
]


@pytest.mark.parametrize(
    "ruff_table, source, expected_exit, expected_bans", RUFF_TABLES
)
def test_ruff_reads_every_option_of_its_table(
    tmp_path: Path,
    ruff_table: str,
    source: str,
    expected_exit: int,
    expected_bans: int,
) -> None:
    repository(tmp_path)
    link_toolkit_tool(tmp_path, "ruff")
    link_toolkit_tool(tmp_path, "pylint")
    stage_file(tmp_path, "svc/src/settings.py", source)

    finished = run_configured(
        tmp_path, f'source_directories = ["svc/src"]\n{ruff_table}', "linters"
    )

    assert finished.returncode == expected_exit, finished.stdout
    assert finished.stdout.count("is banned") == expected_bans


@pytest.mark.parametrize(
    "source_directories, expected_exit",
    [('["svc/src"]', 0), ('["svc/src", "svc/tests"]', 1)],
)
def test_lints_a_tests_folder_only_when_it_is_a_source_folder(
    tmp_path: Path, source_directories: str, expected_exit: int
) -> None:
    repository(tmp_path)
    link_toolkit_tool(tmp_path, "ruff")
    link_toolkit_tool(tmp_path, "pylint")
    stage_file(tmp_path, "svc/src/settings.py", "VALUE = 1\n")
    stage_file(tmp_path, "svc/tests/test_settings.py", "import os\n")

    finished = run_configured(
        tmp_path, f"source_directories = {source_directories}\n", "linters"
    )

    assert finished.returncode == expected_exit, finished.stdout
    assert ("svc/tests/test_settings.py" in finished.stdout) == bool(
        expected_exit
    )
