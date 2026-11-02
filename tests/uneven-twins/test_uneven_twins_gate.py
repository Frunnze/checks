from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.uneven-twins]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, width: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/size.py",
        "def size(first_row, last_row, first_column, last_column):\n"
        f"    width = {width}\n"
        "    height = int(last_row - first_row) + 1\n"
        "    return width, height\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "uneven-twins")

    return finished.returncode, finished.stderr


def test_failure_names_the_missing_step(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(
        tmp_path, "int(last_column - first_column)"
    )

    assert returncode == 1
    assert (
        "user-service/src/size.py:2: width = int(last_column - first_column)"
        " lacks the + 1 of its twin on line 3 - add the + 1 here or drop it"
        " from the twin" in stderr
    )
    assert "twin has" in stderr


def test_passes_twins_that_agree(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(
        tmp_path, "int(last_column - first_column) + 1"
    )

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "uneven-twins")

    assert finished.returncode != 0
