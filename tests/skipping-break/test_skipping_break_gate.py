from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.skipping-break]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, keyword: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/names.py",
        "def unique_names(users):\n"
        "    seen = set()\n"
        "    for user in users:\n"
        "        if user.name in seen:\n"
        f"            {keyword}\n"
        "        seen.add(user.name)\n"
        "    return seen\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "skipping-break")

    return finished.returncode, finished.stderr


def test_failure_names_the_skipped_item(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "break")

    assert returncode == 1
    assert (
        "user-service/src/names.py:5: break ends the whole loop when"
        " user.name was already seen, so the items after it are never"
        " looked at - use continue to skip only this one" in stderr
    )
    assert "use continue" in stderr


def test_passes_a_continue(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "continue")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "skipping-break")

    assert finished.returncode != 0
