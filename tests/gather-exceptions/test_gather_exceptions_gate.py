from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.gather-exceptions]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, keyword: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/fetching.py",
        "import asyncio\n"
        "async def fetch_all(jobs):\n"
        "    results: list[str | BaseException] = await asyncio.gather(\n"
        f"        *jobs{keyword}\n"
        "    )\n"
        "    return results\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "gather-exceptions")

    return finished.returncode, finished.stderr


def test_failure_names_the_result_typed_with_exceptions(
    tmp_path: Path,
) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/fetching.py:3: results is typed to hold"
        " exceptions, but gather without return_exceptions=True raises the"
        " first one instead of returning it" in stderr
    )
    assert "pass return_exceptions=True" in stderr


def test_passes_returned_exceptions(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, ", return_exceptions=True")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "gather-exceptions")

    assert finished.returncode != 0
