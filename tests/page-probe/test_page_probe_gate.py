from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.page-probe]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, fetched: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/paging.py",
        "def page(repository, limit):\n"
        f"    rows = repository.find(limit={fetched})\n"
        "    return rows[:limit], len(rows) > limit\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "page-probe")

    return finished.returncode, finished.stderr


def test_failure_names_the_unreachable_test(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "limit")

    assert returncode == 1
    assert (
        "user-service/src/paging.py:2: rows holds at most limit items, so"
        " len(rows) > limit on line 3 is never true" in stderr
    )
    assert "fetch one more" in stderr


def test_passes_a_look_ahead_row(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "limit + 1")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "page-probe")

    assert finished.returncode != 0
