import subprocess
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import (
    COPIED_TOOLKIT,
    HYPOTHESIS_SETTINGS,
    repository,
    stage_file,
)

OVERLONG_SOURCE = "VALUE = 1\n" * 301


def _run(tmp_path: Path, configuration: str) -> subprocess.CompletedProcess[str]:
    _ = (tmp_path / "checks.toml").write_text(configuration, encoding="utf-8")

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "file-length"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fails_without_a_configuration_file(tmp_path: Path) -> None:
    repository(tmp_path)

    finished = subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert finished.returncode == 1
    assert "no checks.toml" in finished.stderr


def test_fails_on_a_folder_with_no_supported_language(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "worker/src/main.go", "package main\n")

    finished = _run(tmp_path, 'source_directories = ["worker/src"]\n')

    assert finished.returncode == 1
    assert ".go" in finished.stderr
    assert "no check can run" in finished.stderr


def test_names_an_unsupported_language_beside_a_supported_one(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "web/src/app.ts", "export const value = 1;\n")
    stage_file(tmp_path, "web/src/legacy.js", "var value = 1;\n")

    finished = _run(tmp_path, 'source_directories = ["web/src"]\n')

    assert finished.returncode == 0
    assert ".js" in finished.stderr


def test_fails_on_a_configured_folder_that_does_not_exist(
    tmp_path: Path,
) -> None:
    repository(tmp_path)

    finished = _run(tmp_path, 'source_directories = ["missing/src"]\n')

    assert finished.returncode == 1
    assert "missing/src" in finished.stderr


def test_checks_every_listed_service(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "first-service/src/short.py", "VALUE = 1\n")
    stage_file(tmp_path, "second-service/src/long.php", OVERLONG_SOURCE)

    finished = _run(
        tmp_path,
        'source_directories = ["first-service/src", "second-service/src"]\n',
    )

    assert finished.returncode == 1
    assert "second-service/src/long.php" in finished.stderr


def test_a_disabled_check_never_runs(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)

    finished = _run(
        tmp_path,
        'source_directories = ["service/src"]\n'
        '[checks.file-length]\nwhen = "off"\n',
    )

    assert finished.returncode == 0


def test_a_whitelisted_file_passes_the_length_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)

    finished = _run(
        tmp_path,
        'source_directories = ["service/src"]\n'
        '[checks.file-length]\nwhitelist = ["service/src/long.py"]\n',
    )

    assert finished.returncode == 0


@HYPOTHESIS_SETTINGS
@given(st.integers(min_value=1, max_value=400))
def test_run_property_fails_exactly_when_a_file_passes_the_line_limit(
    tmp_path: Path, maximum_lines: int
) -> None:
    project = tmp_path / str(maximum_lines)
    project.mkdir()
    repository(project)
    stage_file(project, "service/src/module.py", "VALUE = 1\n" * 300)

    finished = _run(
        project,
        'source_directories = ["service/src"]\n'
        f"[checks.file-length]\nmax-lines = {maximum_lines}\n",
    )

    assert finished.returncode == int(maximum_lines < 300)


def _run_at_stage(
    tmp_path: Path, configuration: str, stage: str
) -> subprocess.CompletedProcess[str]:
    _ = (tmp_path / "checks.toml").write_text(configuration, encoding="utf-8")

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "--stage", stage, "file-length"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def _commit(tmp_path: Path) -> None:
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "seed"], cwd=tmp_path, check=True
    )


def test_a_pre_push_check_is_skipped_on_pre_commit(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)
    configuration = (
        'source_directories = ["service/src"]\n'
        '[checks.file-length]\nwhen = "pre-push"\n'
    )

    pre_commit = _run_at_stage(tmp_path, configuration, "pre-commit")
    pre_push = _run_at_stage(tmp_path, configuration, "pre-push")

    assert pre_commit.returncode == 0
    assert pre_push.returncode == 1


def test_changed_scope_ignores_an_unstaged_old_problem(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)
    _commit(tmp_path)
    stage_file(tmp_path, "service/src/short.py", "VALUE = 1\n")

    finished = _run_at_stage(
        tmp_path,
        'source_directories = ["service/src"]\n'
        '[checks.file-length]\nscope = "changed"\n',
        "pre-commit",
    )

    assert finished.returncode == 0


def test_changed_scope_reports_a_staged_problem(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/short.py", "VALUE = 1\n")
    _commit(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)

    finished = _run_at_stage(
        tmp_path,
        'source_directories = ["service/src"]\n'
        '[checks.file-length]\nscope = "changed"\n',
        "pre-commit",
    )

    assert finished.returncode == 1
    assert "service/src/long.py" in finished.stderr


def test_repository_scope_reports_an_old_problem(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)
    _commit(tmp_path)

    finished = _run_at_stage(
        tmp_path, 'source_directories = ["service/src"]\n', "pre-commit"
    )

    assert finished.returncode == 1


def test_ci_runs_a_pre_push_check_over_the_whole_repository(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/long.py", OVERLONG_SOURCE)
    _commit(tmp_path)

    finished = _run_at_stage(
        tmp_path,
        'source_directories = ["service/src"]\n'
        '[checks.file-length]\nwhen = "pre-push"\nscope = "changed"\n',
        "ci",
    )

    assert finished.returncode == 1


def test_a_check_uses_its_own_folders_over_the_global_ones(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "first/src/long.py", OVERLONG_SOURCE)
    stage_file(tmp_path, "second/src/short.py", "VALUE = 1\n")

    finished = _run(
        tmp_path,
        'source_directories = ["first/src", "second/src"]\n'
        '[checks.file-length]\nsource_directories = ["second/src"]\n',
    )

    assert finished.returncode == 0
