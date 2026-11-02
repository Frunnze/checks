from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.lost-fraction]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, operator: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/shape.py",
        "def wide(width, height):\n"
        f"    return width {operator} height > 1.5\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "lost-fraction")

    return finished.returncode, finished.stderr


def test_failure_names_the_whole_and_the_fraction(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "//")

    assert returncode == 1
    assert (
        "user-service/src/shape.py:2: width // height has lost its fraction"
        " but is compared with 1.5" in stderr
    )


def test_passes_true_division(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "/")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "lost-fraction")

    assert finished.returncode != 0
