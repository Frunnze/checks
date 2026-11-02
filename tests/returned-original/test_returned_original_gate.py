from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.returned-original]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, returned: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/labels.py",
        "def label(rows):\n"
        "    labelled = list(rows)\n"
        "    labelled[0] = labelled[0].upper()\n"
        f"    return {returned}\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "returned-original")

    return finished.returncode, finished.stderr


def test_failure_names_the_dropped_copy(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "rows")

    assert returncode == 1
    assert (
        "user-service/src/labels.py:4: returns rows unchanged, but its copy"
        " labelled (line 2) was changed - return labelled instead" in stderr
    )
    assert "return the changed copy" in stderr


def test_passes_a_function_that_returns_the_copy(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "labelled")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "returned-original")

    assert finished.returncode != 0
