from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unbounded-fetch]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, bound: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/snapshots.py",
        "def latest(cursor):\n"
        f"    cursor.execute('SELECT * FROM s ORDER BY id DESC{bound}')\n"
        "    return cursor.fetchone()\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unbounded-fetch")

    return finished.returncode, finished.stderr


def test_failure_names_the_query_and_the_fetch(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/snapshots.py:2: this ordered query has no LIMIT"
        " but line 3 keeps only one row" in stderr
    )


def test_passes_a_limited_query(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, " LIMIT 1")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unbounded-fetch")

    assert finished.returncode != 0
