from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.stalled-loop]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, skip: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/answers.py",
        "def answer_index(messages, start):\n"
        "    index = start\n"
        "    while index < len(messages):\n"
        "        if not messages[index]:\n"
        f"{skip}"
        "            continue\n"
        "        index += 1\n"
        "    return index\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "stalled-loop")

    return finished.returncode, finished.stderr


def test_failure_names_the_stalled_path(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/answers.py:5: this path returns to the loop test"
        " on line 3 without changing anything the test reads" in stderr
    )


def test_passes_a_path_that_moves_on(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "            index += 1\n")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "stalled-loop")

    assert finished.returncode != 0
