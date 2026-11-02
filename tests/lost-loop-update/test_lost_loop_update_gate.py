from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.lost-loop-update]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, update: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/pages.py",
        "def collect(pages):\n"
        "    items = []\n"
        "    for page in pages:\n"
        f"        {update}\n"
        "    return items\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "lost-loop-update")

    return finished.returncode, finished.stderr


def test_failure_names_the_replaced_value(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "items = page.items()")

    assert returncode == 1
    assert (
        "user-service/src/pages.py:4: items is replaced on every pass, so"
        " only the last is kept - add to items instead of replacing it"
        in stderr
    )
    assert "throw away the work of earlier passes" in stderr


def test_passes_a_loop_that_adds_to_the_value(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "items.extend(page.items())")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "lost-loop-update")

    assert finished.returncode != 0
