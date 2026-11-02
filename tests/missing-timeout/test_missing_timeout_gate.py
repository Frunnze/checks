from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.missing-timeout]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, options: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/cache.py",
        "import redis\n"
        "def build_cache(url):\n"
        f"    return redis.from_url(url, {options})\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "missing-timeout")

    return finished.returncode, finished.stderr


def test_failure_names_the_missing_option(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "socket_connect_timeout=2")

    assert returncode == 1
    assert (
        "user-service/src/cache.py:3: redis.from_url() has no"
        " socket_timeout, so a stalled peer blocks it forever" in stderr
    )
    assert "wait forever" in stderr


def test_passes_a_client_with_a_timeout(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "socket_timeout=5")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "missing-timeout")

    assert finished.returncode != 0
