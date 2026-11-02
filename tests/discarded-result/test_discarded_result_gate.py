from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.discarded-result]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, cleaning: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/names.py",
        "def display_name(name: str) -> str:\n"
        f"    {cleaning}\n"
        "    return name\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "discarded-result")

    return finished.returncode, finished.stderr


def test_failure_names_the_thrown_away_call(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "name.strip()")

    assert returncode == 1
    assert (
        "user-service/src/names.py:2: the result of name.strip() is thrown"
        " away - str values never change in place" in stderr
    )
    assert "assign" in stderr


def test_passes_an_assigned_result(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "name = name.strip()")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "discarded-result")

    assert finished.returncode != 0
