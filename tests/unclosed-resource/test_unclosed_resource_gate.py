from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unclosed-resource]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, release: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/probe.py",
        "import httpx\n"
        "def is_up(url):\n"
        "    client = httpx.Client()\n"
        "    status = client.get(url).status_code\n"
        f"{release}"
        "    return status == 200\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unclosed-resource")

    return finished.returncode, finished.stderr


def test_failure_names_the_resource(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/probe.py:3: client = httpx.Client(...) is never"
        " closed, returned or handed on" in stderr
    )


def test_passes_a_closed_resource(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "    client.close()\n")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unclosed-resource")

    assert finished.returncode != 0
