from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.failure-as-success]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, answer: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/mailer.py",
        "def send_receipt(smtp, order) -> bool:\n"
        "    try:\n"
        "        smtp.send(order)\n"
        "    except ConnectionError:\n"
        f"        return {answer}\n"
        "    return True\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "failure-as-success")

    return finished.returncode, finished.stderr


def test_failure_names_the_action(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "True")

    assert returncode == 1
    assert (
        "user-service/src/mailer.py:5: send_receipt() answers True from an"
        " except" in stderr
    )


def test_passes_an_honest_failure(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "False")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "failure-as-success")

    assert finished.returncode != 0
