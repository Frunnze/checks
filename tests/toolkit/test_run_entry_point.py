import subprocess
from pathlib import Path

import pytest

from check_support import COPIED_TOOLKIT, repository, stage_file

OVERLONG_SOURCE = "VALUE = 1\n" * 301
CONFIGURATION = 'source_directories = ["service/src"]\n'
CHANGED_SCOPE = CONFIGURATION + '[checks.file-length]\nscope = "changed"\n'


def _run(
    project_root: Path, configuration: str, arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    _ = (project_root / "checks.toml").write_text(
        configuration, encoding="utf-8"
    )

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", *arguments],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _commit(project_root: Path) -> None:
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "seed"],
        cwd=project_root,
        check=True,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["file-lenght"],
        ["", ""],
        ["linters/pylint"],
        ["--stage=pre-push"],
        ["--stage", "pre_commit", "file-length"],
        ["--stage", "", "file-length"],
        ["--stage"],
    ],
)
def test_rejects_an_unknown_check_or_stage(
    tmp_path: Path, arguments: list[str]
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)

    finished = _run(tmp_path, CONFIGURATION, arguments)

    assert finished.returncode == 1
    assert "pre-commit:" in finished.stderr
    assert "long.py" not in finished.stderr


def test_runs_the_checks_of_a_project_whose_path_has_a_space(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "my projects" / "repo"
    project_root.mkdir(parents=True)
    repository(project_root)
    stage_file(project_root, "service/src/long.py", OVERLONG_SOURCE)

    finished = _run(project_root, CONFIGURATION, ["file-length"])

    assert finished.returncode == 1
    assert "service/src/long.py (301 lines)" in finished.stderr


def test_changed_scope_checks_a_staged_file_with_a_non_ascii_name(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/short.py", "VALUE = 1\n")
    _commit(tmp_path)
    stage_file(tmp_path, "service/src/café.py", OVERLONG_SOURCE)

    finished = _run(
        tmp_path, CHANGED_SCOPE, ["--stage", "pre-commit", "file-length"]
    )

    assert finished.returncode == 1
    assert "service/src/café.py (301 lines)" in finished.stderr


def test_changed_scope_checks_the_tests_of_a_root_source_folder(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "src/short.py", "VALUE = 1\n")
    _commit(tmp_path)
    stage_file(tmp_path, "tests/test_long.py", OVERLONG_SOURCE)

    finished = _run(
        tmp_path,
        'source_directories = ["src"]\n'
        '[checks.file-length]\nscope = "changed"\n',
        ["--stage", "pre-commit", "file-length"],
    )

    assert finished.returncode == 1
    assert "tests/test_long.py (301 lines)" in finished.stderr


def test_changed_scope_ignores_an_old_file_that_shares_a_name_prefix(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/view.tsx", OVERLONG_SOURCE)
    _commit(tmp_path)
    stage_file(tmp_path, "service/src/view.ts", "export const a = 1;\n")

    finished = _run(
        tmp_path, CHANGED_SCOPE, ["--stage", "pre-commit", "file-length"]
    )

    assert finished.returncode == 0
