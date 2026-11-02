from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.cache-across-users]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, owner: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/views.py",
        "from functools import cache\n"
        "from flask import g\n"
        "@cache\n"
        "def projects(user_id):\n"
        f"    return load(owner={owner})\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "cache-across-users")

    return finished.returncode, finished.stderr


def test_failure_names_the_cached_function(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "g.user.id")

    assert returncode == 1
    assert (
        "user-service/src/views.py:4: projects() is cached by its arguments"
        " but reads g" in stderr
    )


def test_passes_a_user_passed_in(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "user_id")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "cache-across-users")

    assert finished.returncode != 0
