import json
import subprocess
import sys
from pathlib import Path

import pytest
from check_support import link_real_python, repository, run_check
from srp_support import CHECK, mixed_function, unit_named
from srp_whitelist_support import (
    WORKER_CLASS_NAME,
    WORKER_REASON,
    reviewed_worker_source,
    scan_with_whitelist,
    whitelist_text,
    worker_whitelist_entry,
)


@pytest.mark.parametrize("spelling", ["relative", "absolute", "symlink"])
def test_whitelist_exempts_only_the_reviewed_unit_and_preserves_its_evidence(
    tmp_path: Path, spelling: str
) -> None:
    source = tmp_path / "source with spaces.py"
    source.write_text(reviewed_worker_source())
    path = source.name if spelling == "relative" else str(source)
    if spelling == "symlink":
        alias = tmp_path / "alias.py"
        alias.symlink_to(source)
        path = str(alias)
    entries_text = whitelist_text([worker_whitelist_entry(path)])

    result = scan_with_whitelist(tmp_path, entries_text, [tmp_path])
    report = json.loads(result.stdout)
    unit = unit_named(report, WORKER_CLASS_NAME)

    assert result.returncode == 0, result.stderr
    assert report["coefficient"] < 0.5
    assert report["raw_coefficient"] == 0.5
    assert report["whitelisted_count"] == 1
    assert len(report["files"]) == 1
    assert report["files"][0]["raw_coefficient"] == 0.5
    assert unit["coefficient"] == 0.5
    assert unit["whitelisted"]
    assert unit["whitelist_reason"] == WORKER_REASON
    assert unit["reasons"]


@pytest.mark.parametrize("location", ["same_file", "other_file"])
def test_whitelist_does_not_suppress_other_findings(
    tmp_path: Path, location: str
) -> None:
    source = tmp_path / "worker.py"
    source.write_text(reviewed_worker_source())
    if location == "same_file":
        source.write_text(source.read_text() + "\n" + mixed_function())
    else:
        (tmp_path / "another.py").write_text(reviewed_worker_source())
    entries_text = whitelist_text([worker_whitelist_entry()])

    result = scan_with_whitelist(tmp_path, entries_text, [tmp_path])
    report = json.loads(result.stdout)

    assert result.returncode == 1
    assert report["failed"]
    assert report["coefficient"] >= 0.5
    assert report["whitelisted_count"] == 1
    assert any(
        unit["coefficient"] >= 0.5 and not unit["whitelisted"]
        for file in report["files"]
        for unit in file["units"]
    )


def test_whitelist_path_wildcards_match_nothing(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(reviewed_worker_source())
    entries_text = whitelist_text([worker_whitelist_entry(path="*.py")])

    result = scan_with_whitelist(tmp_path, entries_text, [tmp_path])
    report = json.loads(result.stdout)

    assert result.returncode == 1
    assert report["whitelisted_count"] == 0


@pytest.mark.parametrize("changes", [{"name": "*"}, {"kind": "module"}])
def test_whitelist_matches_exact_kind_and_name(
    tmp_path: Path, changes: dict[str, str]
) -> None:
    (tmp_path / "worker.py").write_text(reviewed_worker_source())
    entries_text = whitelist_text([worker_whitelist_entry(**changes)])

    result = scan_with_whitelist(tmp_path, entries_text, [tmp_path])

    assert result.returncode == 2
    assert "stale SRP whitelist entry" in result.stderr


INVALID_ENTRY_CHANGES: dict[str, dict[str, object]] = {
    "empty_reason": {"reason": "  "},
    "nonstring": {"name": [WORKER_CLASS_NAME]},
    "kind": {"kind": "file"},
    "extra": {"anything": "typo"},
    "empty_entities": {"entities": []},
    "string_entities": {"entities": "network"},
    "nonstring_entity": {"entities": ["network", 1]},
    "unsorted_entities": {"entities": ["network", "filesystem"]},
    "repeated_entities": {"entities": ["network", "network"]},
}


INVALID_WHITELIST_PROBLEMS = [
    *INVALID_ENTRY_CHANGES,
    "missing_reason",
    "missing_entities",
    "duplicate",
]


@pytest.mark.parametrize("problem", INVALID_WHITELIST_PROBLEMS)
def test_invalid_whitelists_are_analysis_errors(
    tmp_path: Path, problem: str
) -> None:
    (tmp_path / "worker.py").write_text(reviewed_worker_source())
    entry = worker_whitelist_entry(**INVALID_ENTRY_CHANGES.get(problem, {}))
    if problem == "missing_reason":
        del entry["reason"]
    if problem == "missing_entities":
        del entry["entities"]
    entries = [entry, entry] if problem == "duplicate" else [entry]

    result = scan_with_whitelist(
        tmp_path, whitelist_text(entries), [tmp_path]
    )

    assert result.returncode == 2
    assert "invalid SRP whitelist" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("contents", [None, "{broken json}\n"])
def test_missing_or_malformed_whitelist_cannot_pass(
    tmp_path: Path, contents: str | None
) -> None:
    whitelist = tmp_path / "whitelist.txt"
    if contents is not None:
        whitelist.write_text(contents)
    result = subprocess.run(
        [
            sys.executable,
            str(CHECK / "srp_check.py"),
            "--json",
            "--whitelist",
            str(whitelist),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "SRP analysis error" in result.stderr
    assert result.stdout == ""


def test_hook_reads_adjacent_whitelist_and_instructs_the_agent(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    source = tmp_path / "user-service/src/worker.py"
    source.parent.mkdir(parents=True)
    source.write_text(reviewed_worker_source())
    entry = worker_whitelist_entry("user-service/src/worker.py")
    inline_entry = ", ".join(
        f"{key} = {json.dumps(value)}" for key, value in entry.items()
    )
    whitelist_setting = f"whitelist = [{{ {inline_entry} }}]\n"

    result = run_check(
        tmp_path,
        "single-responsibility",
        {"single-responsibility": whitelist_setting},
    )

    assert result.returncode == 0, result.stderr
    assert "whitelisted=1" in result.stdout
    assert (
        "Agent: first identify whether each finding is a real"
        in result.stdout
    )
    assert "Split only the real violations" in result.stdout
    assert "never refactor it" in result.stdout
    assert "[checks.single-responsibility] whitelist" in result.stdout
