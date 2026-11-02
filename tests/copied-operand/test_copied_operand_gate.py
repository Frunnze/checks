from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.copied-operand]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, last_index: int) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/colors.py",
        "def expand(v):\n"
        f"    return v[0] * 2 + v[1] * 2 + v[{last_index}] * 2\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "copied-operand")

    return finished.returncode, finished.stderr


def test_failure_names_the_repeated_operand(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, 1)

    assert returncode == 1
    assert (
        "user-service/src/colors.py:2: v[1] * 2 - its siblings step through"
        " indexes but it repeats one" in stderr
    )


def test_passes_a_complete_series(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, 2)

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "copied-operand")

    assert finished.returncode != 0
