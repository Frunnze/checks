import json
import os
import subprocess
import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import (
    COPIED_TOOLKIT,
    DART_PUBSPEC,
    HYPOTHESIS_SETTINGS,
    repository,
    stage_file,
)

UNREACHABLE_ERROR = (
    "Error during extraction: max retries exceeded: request failed: "
    'Post "https://api.osv.dev/v1/querybatch": dial tcp: lookup '
    "api.osv.dev: no such host\n"
)
BROKEN_LOCKFILE_ERROR = "failed to parse pubspec.lock: yaml: line 3\n"
CLEAN_REPORT = '{"results": []}'
advisory_numbers = st.sets(
    st.integers(min_value=1000, max_value=9999), min_size=1, max_size=4
)
advisory_ids = st.lists(
    st.from_regex(r"GHSA-[a-z0-9]{4}-[a-z0-9]{4}", fullmatch=True),
    max_size=3,
)
package_names = st.from_regex(r"[a-z]{3,10}", fullmatch=True)


def _advisory(number: int) -> dict[str, object]:
    return {
        "id": f"GHSA-dart-{number}",
        "aliases": [f"CVE-2026-{number}"],
        "summary": f"flaw {number}",
    }


def _report(numbers: set[int]) -> str:
    vulnerabilities: list[dict[str, object]] = []

    for number in sorted(numbers):
        vulnerabilities.append(_advisory(number))

    package = {
        "package": {"name": "http", "version": "0.12.0", "ecosystem": "Pub"},
        "vulnerabilities": vulnerabilities,
    }

    return json.dumps({"results": [{"packages": [package]}]})


def _printing_stub(report: str, exit_code: int) -> str:
    return f"printf '%s\\n' '{report}'\nexit {exit_code}\n"


def _prepare(
    root: Path,
    stub_body: str,
    whitelist: list[str],
    packages: tuple[str, ...],
) -> None:
    repository(root)
    listed_directories: list[str] = []

    for package in packages:
        stage_file(root, f"{package}/pubspec.yaml", DART_PUBSPEC)
        stage_file(root, f"{package}/lib/main.dart", "void main() {}\n")
        listed_directories.append(f"{package}/lib")

    scanner = root / "stubs" / "osv-scanner"
    scanner.parent.mkdir()
    _ = scanner.write_text(f"#!/bin/sh\n{stub_body}", encoding="utf-8")
    scanner.chmod(0o755)
    configuration = (
        f"source_directories = {json.dumps(listed_directories)}\n"
        f"[checks.vulnerable-deps]\nwhitelist = {json.dumps(whitelist)}\n"
    )
    _ = (root / "checks.toml").write_text(configuration, encoding="utf-8")


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    stubs = root / "stubs"

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "vulnerable-deps"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"},
    )


def _scan(
    root: Path,
    stub_body: str,
    whitelist: list[str],
    packages: tuple[str, ...] = ("app",),
) -> subprocess.CompletedProcess[str]:
    _prepare(root, stub_body, whitelist, packages)

    for package in packages:
        stage_file(root, f"{package}/pubspec.lock", "packages: {}\n")

    return _run(root)


def _accepted_names(numbers: set[int], by_alias: bool) -> list[str]:
    accepted: list[str] = []

    for number in sorted(numbers):
        if by_alias:
            accepted.append(f"CVE-2026-{number}")
        else:
            accepted.append(f"GHSA-dart-{number}")

    return accepted


@HYPOTHESIS_SETTINGS
@given(advisory_numbers, st.data(), st.booleans())
def test_vulnerable_deps_property_reports_exactly_the_unaccepted_advisories(
    numbers: set[int], data: st.DataObject, by_alias: bool
) -> None:
    accepted_numbers = data.draw(st.sets(st.sampled_from(sorted(numbers))))
    whitelist = _accepted_names(accepted_numbers, by_alias)
    stub_body = _printing_stub(_report(numbers), 1)

    with tempfile.TemporaryDirectory() as directory:
        finished = _scan(Path(directory), stub_body, whitelist)

    unaccepted = numbers - accepted_numbers
    assert finished.returncode == int(bool(unaccepted)), finished.stderr

    for number in numbers:
        is_reported = f"GHSA-dart-{number}" in finished.stderr
        assert is_reported == (number in unaccepted)


@HYPOTHESIS_SETTINGS
@given(st.sampled_from([UNREACHABLE_ERROR, BROKEN_LOCKFILE_ERROR]))
def test_vulnerable_deps_property_skips_only_an_unreachable_database(
    scanner_error: str,
) -> None:
    stub_body = f"cat >&2 <<'ERROR'\n{scanner_error}ERROR\nexit 127\n"

    with tempfile.TemporaryDirectory() as directory:
        finished = _scan(Path(directory), stub_body, [])

    is_unreachable = scanner_error == UNREACHABLE_ERROR
    assert finished.returncode == int(not is_unreachable), finished.stderr
    assert ("unreachable" in finished.stderr) == is_unreachable


@HYPOTHESIS_SETTINGS
@given(advisory_ids)
def test_vulnerable_deps_property_passes_a_clean_scan_whatever_the_whitelist(
    whitelist: list[str],
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        finished = _scan(
            Path(directory), _printing_stub(CLEAN_REPORT, 0), whitelist
        )

    assert finished.returncode == 0, finished.stderr


@HYPOTHESIS_SETTINGS
@given(package_names)
def test_vulnerable_deps_property_fails_fast_without_a_dart_lockfile(
    package: str,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _prepare(root, _printing_stub(CLEAN_REPORT, 0), [], (package,))

        finished = _run(root)

    assert finished.returncode == 1
    assert f"{package} has no pubspec.lock" in finished.stderr


@HYPOTHESIS_SETTINGS
@given(st.sampled_from(["first", "second"]))
def test_vulnerable_deps_property_names_only_the_vulnerable_dart_package(
    vulnerable_package: str,
) -> None:
    vulnerable_scan = _printing_stub(_report({1234}), 1)
    stub_body = (
        'case "$*" in\n'
        f'    *"{vulnerable_package}/pubspec.lock"*)\n{vulnerable_scan};;\n'
        "esac\n"
        f"{_printing_stub(CLEAN_REPORT, 0)}"
    )

    with tempfile.TemporaryDirectory() as directory:
        finished = _scan(
            Path(directory), stub_body, [], ("first", "second")
        )

    assert finished.returncode == 1, finished.stderr
    assert f"a package in {vulnerable_package} has" in finished.stderr
