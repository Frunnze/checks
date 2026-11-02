from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.mac-comparison]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, check: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/webhook.py",
        "import hmac\n"
        "def valid(key, body, received):\n"
        "    expected = hmac.new(key, body, 'sha256').hexdigest()\n"
        f"    return {check}\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "mac-comparison")

    return finished.returncode, finished.stderr


def test_failure_names_the_mac(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "expected == received")

    assert returncode == 1
    assert (
        "user-service/src/webhook.py:4: expected is an HMAC compared with =="
        in stderr
    )


def test_passes_a_constant_time_check(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(
        tmp_path, "hmac.compare_digest(expected, received)"
    )

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "mac-comparison")

    assert finished.returncode != 0
