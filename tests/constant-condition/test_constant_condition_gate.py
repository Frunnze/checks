from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.constant-condition]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, joiner: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/guard.py",
        "def guard(role):\n"
        f"    if role != 'admin' {joiner} role != 'owner':\n"
        "        raise PermissionError(role)\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "constant-condition")

    return finished.returncode, finished.stderr


def test_failure_names_the_condition(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "or")

    assert returncode == 1
    assert (
        "user-service/src/guard.py:2: role != 'admin' or role != 'owner' is"
        " always true" in stderr
    )


def test_passes_the_intended_guard(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "and")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "constant-condition")

    assert finished.returncode != 0
