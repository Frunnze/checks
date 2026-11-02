from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.blocking-call-in-async]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, call: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/orders.py",
        "import asyncio\n"
        "import time\n"
        "def load_order(order_id):\n"
        "    time.sleep(1)\n"
        "    return order_id\n"
        "@router.get('/orders/{order_id}')\n"
        "async def show_order(order_id):\n"
        f"    return {call}\n",
    )
    finished = run_configured(
        tmp_path, _CONFIGURATION, "blocking-call-in-async"
    )

    return finished.returncode, finished.stderr


def test_failure_names_the_blocking_chain(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "load_order(order_id)")

    assert returncode == 1
    assert (
        "user-service/src/orders.py:8: load_order() blocks the event loop"
        " of a request handler (load_order -> time.sleep())" in stderr
    )
    assert "threadpool" in stderr


def test_passes_an_offloaded_call(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(
        tmp_path, "await asyncio.to_thread(load_order, order_id)"
    )

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(
        tmp_path, _CONFIGURATION, "blocking-call-in-async"
    )

    assert finished.returncode != 0
