from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.single-pass-loop]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, indent: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/users.py",
        "def find(users, name):\n"
        "    for user in users:\n"
        "        if user.name == name:\n"
        "            print(user)\n"
        f"        {indent}return user\n"
        "    return None\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "single-pass-loop")

    return finished.returncode, finished.stderr


def test_failure_names_the_loop_and_its_exit(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/users.py:2: this loop never gets past its first"
        " item - the exit after the if on line 3 runs for every item"
        in stderr
    )


def test_passes_a_loop_that_can_go_on(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "    ")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "single-pass-loop")

    assert finished.returncode != 0
