from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.mutation-during-iteration]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, iterated: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/orders.py",
        "def drop_cancelled(orders):\n"
        f"    for order in {iterated}:\n"
        "        if order.cancelled:\n"
        "            orders.remove(order)\n",
    )
    finished = run_configured(
        tmp_path, _CONFIGURATION, "mutation-during-iteration"
    )

    return finished.returncode, finished.stderr


def test_failure_names_the_change_and_the_copy(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "orders")

    assert returncode == 1
    assert (
        "user-service/src/orders.py:4: orders.remove() changes orders while"
        " a for loop iterates over it" in stderr
    )
    assert "loop over a copy such as list(orders)" in stderr


def test_passes_a_loop_over_a_copy(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "list(orders)")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(
        tmp_path, _CONFIGURATION, "mutation-during-iteration"
    )

    assert finished.returncode != 0
