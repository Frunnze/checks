from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.permissive-default]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, default: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/settings.py",
        f"import os\nDEBUG = os.getenv('APP_DEBUG', '{default}')\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "permissive-default")

    return finished.returncode, finished.stderr


def test_failure_names_the_setting(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "true")

    assert returncode == 1
    assert (
        "user-service/src/settings.py:2: APP_DEBUG falls back to 'true' when"
        " unset" in stderr
    )


def test_passes_a_safe_default(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "false")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "permissive-default")

    assert finished.returncode != 0
