import json
import os
import subprocess
from pathlib import Path

from check_support import COPIED_TOOLKIT, repository, stage_file

ADVISORY = "GHSA-aaaa-bbbb-cccc"
SOURCE_CONFIGURATION = 'source_directories = ["ui-service/src"]\n'
UNREACHABLE_REPORT = (
    '{"message": "request to https://registry.npmjs.org/-/npm/v1/security/'
    'advisories/bulk failed, reason: getaddrinfo ENOTFOUND", "error": {}}\n'
)
NPM_WARNING = "npm warn Unknown project config \"auto-install-peers\".\n"


def _report(title: str) -> str:
    cause = {
        "name": "netlib",
        "title": title,
        "url": f"https://github.com/advisories/{ADVISORY}",
        "severity": "high",
    }
    vulnerability = {"name": "netlib", "severity": "high", "via": [cause]}

    return json.dumps(
        {"auditReportVersion": 2, "vulnerabilities": {"netlib": vulnerability}}
    )


def _audit(
    tmp_path: Path, report: str, configuration: str = SOURCE_CONFIGURATION
) -> subprocess.CompletedProcess[str]:
    repository(tmp_path)
    stage_file(tmp_path, "ui-service/src/main.ts", "export const a = 1;\n")
    stage_file(tmp_path, "ui-service/package.json", "{}\n")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _ = (stubs / "report.json").write_text(report, encoding="utf-8")
    npm = stubs / "npm"
    _ = npm.write_text(
        f"#!/bin/sh\nprintf '{NPM_WARNING}' >&2\n"
        f'cat "{stubs}/report.json"\nexit 1\n',
        encoding="utf-8",
    )
    npm.chmod(0o755)
    _ = (tmp_path / "checks.toml").write_text(configuration, encoding="utf-8")

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "vulnerable-deps"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"},
    )


def test_fails_on_an_advisory_whose_title_names_the_network(
    tmp_path: Path,
) -> None:
    finished = _audit(tmp_path, _report("Denial of Service over the network"))

    assert finished.returncode == 1
    assert ADVISORY in finished.stderr


def test_passes_a_whitelisted_advisory_while_npm_warns(tmp_path: Path) -> None:
    configuration = (
        SOURCE_CONFIGURATION
        + f'[checks.vulnerable-deps]\nwhitelist = ["{ADVISORY}"]\n'
    )

    finished = _audit(tmp_path, _report("Prototype Pollution"), configuration)

    assert finished.returncode == 0


def test_skips_the_scan_when_the_npm_registry_is_unreachable(
    tmp_path: Path,
) -> None:
    finished = _audit(tmp_path, UNREACHABLE_REPORT)

    assert finished.returncode == 0
    assert "unreachable" in finished.stderr
