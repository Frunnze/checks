from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.float-drift]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, step: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/budget.py",
        "def spend(budget):\n"
        f"    budget -= {step}\n"
        "    return budget <= 0\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "float-drift")

    return finished.returncode, finished.stderr


def test_failure_names_the_total_and_the_step(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "0.1")

    assert returncode == 1
    assert (
        "user-service/src/budget.py:2: budget steps by 0.1, which a binary"
        " float cannot hold exactly, and is compared on line 3" in stderr
    )


def test_passes_a_step_a_float_holds_exactly(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "0.5")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "float-drift")

    assert finished.returncode != 0
