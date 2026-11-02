from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unguarded-state-update]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, where: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/orders.py",
        "def cancel(cursor, order_id):\n"
        "    cursor.execute(\n"
        "        \"UPDATE orders SET status = 'cancelled'\"\n"
        f"        \" WHERE {where}\",\n"
        "        (order_id, 'pending'),\n"
        "    )\n"
        "    return cursor.rowcount == 1\n",
    )
    finished = run_configured(
        tmp_path, _CONFIGURATION, "unguarded-state-update"
    )

    return finished.returncode, finished.stderr


def test_failure_names_the_unguarded_column(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "order_id = %s")

    assert returncode == 1
    assert (
        "user-service/src/orders.py:3: UPDATE sets status but its WHERE"
        " does not test status" in stderr
    )
    assert "the state you read to the WHERE" in stderr


def test_passes_a_compare_and_set(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(
        tmp_path, "order_id = %s AND status = %s"
    )

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(
        tmp_path, _CONFIGURATION, "unguarded-state-update"
    )

    assert finished.returncode != 0
