from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.mixed-clocks]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, clock: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/polling.py",
        "import time\n"
        "def wait_for(job):\n"
        f"    deadline = {clock}() + 5\n"
        "    while not job.done() and time.monotonic() < deadline:\n"
        "        time.sleep(0.1)\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "mixed-clocks")

    return finished.returncode, finished.stderr


def test_failure_names_both_clocks(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "time.time")

    assert returncode == 1
    assert (
        "user-service/src/polling.py:4: time.monotonic() is on the"
        " monotonic clock but deadline (set on line 3) is on the wall"
        " clock" in stderr
    )
    assert "same clock" in stderr


def test_passes_one_clock(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "time.monotonic")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "mixed-clocks")

    assert finished.returncode != 0
