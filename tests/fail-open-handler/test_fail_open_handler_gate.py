from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.fail-open-handler]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, answer: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/gate.py",
        "def is_allowed(user) -> bool:\n"
        "    try:\n"
        "        return user.policy.check()\n"
        "    except TimeoutError:\n"
        f"        return {answer}\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "fail-open-handler")

    return finished.returncode, finished.stderr


def test_failure_names_the_check(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "True")

    assert returncode == 1
    assert (
        "user-service/src/gate.py:5: is_allowed() answers True when it fails"
        in stderr
    )


def test_passes_a_check_that_fails_closed(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "False")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "fail-open-handler")

    assert finished.returncode != 0
