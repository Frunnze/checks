import subprocess
from pathlib import Path

from check_support import (
    here_document,
    link_real_python,
    repository,
    run_check,
    stage_file,
    stub_binary,
)

CLEAN = "No known vulnerabilities found\n"
VULNERABLE = (
    "Found 1 known vulnerability in 1 package\n"
    "Name      Version ID              Fix Versions\n"
    "--------- ------- --------------- ------------\n"
    "starlette 0.49.3  PYSEC-2026-9999 1.3.2\n"
)
VULNERABLE_CONNECTION_POOL = (
    "Found 1 known vulnerability in 1 package\n"
    "Name                     Version ID              Fix Versions\n"
    "------------------------ ------- --------------- ------------\n"
    "django-db-connection-pool 1.2.4  PYSEC-2026-9998 1.2.5\n"
)
OFFLINE = (
    "Traceback (most recent call last):\n"
    "requests.exceptions.ConnectionError: HTTPSConnectionPool("
    "host='pypi.org', port=443): Max retries exceeded\n"
)
CRASHED = (
    "Traceback (most recent call last):\n"
    "KeyError: 'vulns'\n"
)


def _pip_audit_reporting(output: str, status: int) -> str:
    return f"{here_document('AUDIT_EOF', output)}exit {status}\n"


def _check_with(
    tmp_path: Path, output: str, status: int
) -> subprocess.CompletedProcess[str]:
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "user-service/src/service.py", "VALUE = 1\n")
    stub_binary(
        tmp_path, "pip-audit", _pip_audit_reporting(output, status)
    )

    return run_check(tmp_path, "vulnerable-deps")


def test_passes_when_no_vulnerability_is_reported(tmp_path: Path) -> None:
    finished = _check_with(tmp_path, CLEAN, 0)

    assert finished.returncode == 0


def test_fails_on_a_vulnerability_naming_a_connection_pool(
    tmp_path: Path,
) -> None:
    finished = _check_with(tmp_path, VULNERABLE_CONNECTION_POOL, 1)

    assert finished.returncode == 1
    assert "PYSEC-2026-9998" in finished.stderr


def test_fails_on_a_reported_vulnerability(tmp_path: Path) -> None:
    finished = _check_with(tmp_path, VULNERABLE, 1)

    assert finished.returncode == 1
    assert "PYSEC-2026-9999" in finished.stderr


def test_skips_the_scan_when_the_advisory_database_is_unreachable(
    tmp_path: Path,
) -> None:
    finished = _check_with(tmp_path, OFFLINE, 1)

    assert finished.returncode == 0
    assert "unreachable" in finished.stderr


def test_fails_when_pip_audit_crashes_in_a_checkout_named_network(
    tmp_path: Path,
) -> None:
    traceback = (
        'File "/home/me/social-network/.checks/.venv/lib/pip_audit.py"\n'
        + CRASHED
    )

    finished = _check_with(tmp_path, traceback, 1)

    assert finished.returncode == 1


def test_fails_when_pip_audit_crashes_for_another_reason(
    tmp_path: Path,
) -> None:
    finished = _check_with(tmp_path, CRASHED, 1)

    assert finished.returncode == 1
    assert "KeyError" in finished.stderr
