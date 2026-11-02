from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unnormalized-guard]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, tested: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/names.py",
        "def require_name(name):\n"
        "    clean_name = name.strip()\n"
        f"    if not {tested}:\n"
        "        raise ValueError('name is required')\n"
        "    return clean_name\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unnormalized-guard")

    return finished.returncode, finished.stderr


def test_failure_names_the_raw_and_the_normalized_value(
    tmp_path: Path,
) -> None:
    returncode, stderr = _gate_run(tmp_path, "name")

    assert returncode == 1
    assert (
        "user-service/src/names.py:3: the guard tests name for emptiness but"
        " the code goes on with clean_name = name.strip() - a"
        " whitespace-only name passes; test clean_name instead" in stderr
    )
    assert "test the normalized name instead" in stderr


def test_passes_a_guard_on_the_normalized_value(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "clean_name")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unnormalized-guard")

    assert finished.returncode != 0
