from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.path-containment]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, name: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/files.py",
        "import os\n"
        "@app.get('/files/{name}')\n"
        "def download(name):\n"
        f"    return open(os.path.join('/srv/files', {name})).read()\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "path-containment")

    return finished.returncode, finished.stderr


def test_failure_names_the_handler(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "name")

    assert returncode == 1
    assert (
        "user-service/src/files.py:4: download() joins the request value"
        " name" in stderr
    )


def test_passes_a_contained_name(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "os.path.basename(name)")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "path-containment")

    assert finished.returncode != 0
