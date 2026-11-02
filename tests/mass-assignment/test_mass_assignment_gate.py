from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.mass-assignment]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, guard: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/accounts.py",
        "def update_account(account, changes):\n"
        "    for field, value in changes.items():\n"
        f"{guard}"
        "        setattr(account, field, value)\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "mass-assignment")

    return finished.returncode, finished.stderr


def test_failure_names_the_source_and_target(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/accounts.py:2: every key of changes is set on"
        " account" in stderr
    )


def test_passes_an_allowlisted_copy(tmp_path: Path) -> None:
    guard = (
        "        if field not in ('name', 'email'):\n"
        "            continue\n"
    )
    returncode, stderr = _gate_run(tmp_path, guard)

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "mass-assignment")

    assert finished.returncode != 0
