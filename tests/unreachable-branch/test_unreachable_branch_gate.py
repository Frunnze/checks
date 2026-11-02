from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unreachable-branch]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, first: int, second: int) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/quota.py",
        "def level(usage):\n"
        f"    if usage >= {first}:\n        return 'a'\n"
        f"    elif usage >= {second}:\n        return 'b'\n"
        "    return 'c'\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unreachable-branch")

    return finished.returncode, finished.stderr


def test_failure_names_the_branch_and_what_covers_it(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, 80, 100)

    assert returncode == 1
    assert (
        "user-service/src/quota.py:4: this branch never runs - line 2"
        " already takes all its cases" in stderr
    )


def test_passes_conditions_in_narrowing_order(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, 100, 80)

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unreachable-branch")

    assert finished.returncode != 0
