from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.falsy-number]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, test: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/nearest.py",
        "def better(best: float | None, gap: float) -> bool:\n"
        f"    return {test} or gap < best\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "falsy-number")

    return finished.returncode, finished.stderr


def test_failure_names_the_truth_test(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "not best")

    assert returncode == 1
    assert (
        "user-service/src/nearest.py:2: `not best` treats 0 like None but"
        " best is compared as a number beside it" in stderr
    )


def test_passes_a_none_check(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "best is None")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "falsy-number")

    assert finished.returncode != 0
