from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unchecked-url-fetch]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, check: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/preview.py",
        "import requests\n"
        "@app.get('/preview')\n"
        "def preview(url):\n"
        f"{check}"
        "    return requests.get(url, timeout=5).text\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unchecked-url-fetch")

    return finished.returncode, finished.stderr


def test_failure_names_the_handler(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/preview.py:4: preview() fetches the request value"
        " url" in stderr
    )


def test_passes_a_checked_url(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "    validate_public_url(url)\n")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unchecked-url-fetch")

    assert finished.returncode != 0
