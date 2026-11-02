from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unraised-exception]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, keyword: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/guard.py",
        "from errors import AccessDenied\n"
        "def guard(owner, user):\n"
        "    if owner != user:\n"
        f"        {keyword}AccessDeniedError(user)\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unraised-exception")

    return finished.returncode, finished.stderr


def test_failure_names_the_exception(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/guard.py:4: AccessDeniedError(...) is built but"
        " never raised - add raise" in stderr
    )


def test_passes_a_raised_exception(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "raise ")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unraised-exception")

    assert finished.returncode != 0
