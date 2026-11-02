from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.split-commit]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, middle: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/migrate.py",
        "def apply(connection, cursor, sql, version):\n"
        "    cursor.execute(sql)\n"
        f"{middle}"
        "    cursor.execute('INSERT INTO versions VALUES (%s)', version)\n"
        "    connection.commit()\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "split-commit")

    return finished.returncode, finished.stderr


def test_failure_names_the_early_commit(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "    connection.commit()\n")

    assert returncode == 1
    assert (
        "user-service/src/migrate.py:3: connection.commit() saves part of"
        " the change - the rest is committed on line 5" in stderr
    )


def test_passes_a_single_commit(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "split-commit")

    assert finished.returncode != 0
