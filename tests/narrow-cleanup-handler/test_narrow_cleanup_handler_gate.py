from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.narrow-cleanup-handler]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, caught: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/jobs.py",
        "def submit(lock, store, job):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        store.save(job)\n"
        f"    except {caught}:\n"
        "        lock.release()\n"
        "        raise\n",
    )
    finished = run_configured(
        tmp_path, _CONFIGURATION, "narrow-cleanup-handler"
    )

    return finished.returncode, finished.stderr


def test_failure_names_the_skipped_cleanup(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "KeyError")

    assert returncode == 1
    assert (
        "user-service/src/jobs.py:5: except KeyError runs release() and"
        " re-raises, but any other exception skips it" in stderr
    )
    assert "finally" in stderr


def test_passes_a_handler_that_catches_everything(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "BaseException")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(
        tmp_path, _CONFIGURATION, "narrow-cleanup-handler"
    )

    assert finished.returncode != 0
