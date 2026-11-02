from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.lazy-init-race]\nwhen = "pre-commit"\n'
)
_UNTESTED = "                self._engine = open_engine()\n"
_TESTED_AGAIN = (
    "                if self._engine is None:\n"
    "                    self._engine = open_engine()\n"
)


def _gate_run(tmp_path: Path, lock_body: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/engines.py",
        "import threading\n"
        "class Engines:\n"
        "    def __init__(self):\n"
        "        self._engine = None\n"
        "        self._lock = threading.Lock()\n"
        "    def engine(self):\n"
        "        if self._engine is None:\n"
        "            with self._lock:\n"
        f"{lock_body}"
        "        return self._engine\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "lazy-init-race")

    return finished.returncode, finished.stderr


def test_failure_names_the_value_and_the_lock(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, _UNTESTED)

    assert returncode == 1
    assert (
        "user-service/src/engines.py:8: self._engine is tested before"
        " taking self._lock but set under it without a second test"
        in stderr
    )
    assert "test them again inside the lock" in stderr


def test_passes_a_value_tested_again_under_the_lock(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, _TESTED_AGAIN)

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "lazy-init-race")

    assert finished.returncode != 0
