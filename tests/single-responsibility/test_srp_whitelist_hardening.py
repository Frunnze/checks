import json
from pathlib import Path

from srp_support import mixed_function, unit_named
from srp_whitelist_support import (
    UTF8_BYTE_ORDER_MARK,
    WORKER_CLASS_NAME,
    reviewed_worker_source,
    scan_with_whitelist,
    whitelist_text,
    worker_whitelist_entry,
)


def write_worker(root: Path) -> None:
    source = root / "worker.py"
    source.write_text(reviewed_worker_source())


def test_whitelist_starting_with_a_byte_order_mark_is_accepted(
    tmp_path: Path,
) -> None:
    write_worker(tmp_path)
    entries_text = whitelist_text([worker_whitelist_entry()])
    contents = UTF8_BYTE_ORDER_MARK + entries_text

    result = scan_with_whitelist(tmp_path, contents, [tmp_path])
    report = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert report["whitelisted_count"] == 1


def test_unit_that_gained_an_entity_is_reported_not_suppressed(
    tmp_path: Path,
) -> None:
    write_worker(tmp_path)
    entry = worker_whitelist_entry(entities=["network", "process"])

    result = scan_with_whitelist(tmp_path, whitelist_text([entry]), [tmp_path])
    report = json.loads(result.stdout)
    unit = unit_named(report, WORKER_CLASS_NAME)

    assert result.returncode == 1
    assert report["whitelisted_count"] == 0
    assert not unit["whitelisted"]
    assert "whitelist_reason" not in unit


def test_entry_for_a_vanished_unit_is_an_analysis_error_naming_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "worker.py").write_text(mixed_function())
    entry = worker_whitelist_entry()

    result = scan_with_whitelist(tmp_path, whitelist_text([entry]), [tmp_path])

    assert result.returncode == 2
    assert "SRP analysis error" in result.stderr
    assert "stale SRP whitelist entry" in result.stderr
    assert WORKER_CLASS_NAME in result.stderr
    assert result.stdout == ""


def test_entry_for_a_file_outside_the_scan_is_ignored(tmp_path: Path) -> None:
    write_worker(tmp_path)
    scanned = tmp_path / "scanned.py"
    scanned.write_text("def work():\n    return 1\n")
    entry = worker_whitelist_entry(name="<module>.Vanished")

    result = scan_with_whitelist(tmp_path, whitelist_text([entry]), [scanned])

    assert result.returncode == 0, result.stderr
