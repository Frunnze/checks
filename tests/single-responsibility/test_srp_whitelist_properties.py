import json
import string
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from srp_support import THRESHOLD
from srp_whitelist import (
    WhitelistEntry,
    apply_whitelist,
    parse_entities,
    parse_entry,
    read_whitelist,
    reject_stale_entries,
)
from srp_whitelist_support import UTF8_BYTE_ORDER_MARK

ANALYZED_PATH = Path("/analyzed/worker.py")
UNANALYZED_PATH = Path("/elsewhere/worker.py")
UNIT_KIND = "class"
UNIT_NAME = "<module>.Worker"
REASON = "Reviewed reason."

entity_names = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8)
sorted_entity_lists = st.lists(entity_names, min_size=1, unique=True).map(
    sorted
)
unit_names = st.text(alphabet=string.ascii_letters, min_size=1, max_size=8)


def single_unit_reports(entities: list[str]) -> list[dict[str, Any]]:
    unit = {
        "kind": UNIT_KIND,
        "name": UNIT_NAME,
        "entities": entities,
        "coefficient": THRESHOLD,
    }
    report = {
        "path": str(ANALYZED_PATH),
        "coefficient": THRESHOLD,
        "units": [unit],
    }
    return [report]


def entry_line(entities: list[str], reason: str) -> str:
    fields = {
        "path": str(ANALYZED_PATH),
        "kind": UNIT_KIND,
        "name": UNIT_NAME,
        "entities": entities,
        "reason": reason,
    }
    return json.dumps(fields)


@given(sorted_entity_lists, st.booleans())
def test_read_whitelist_property_round_trips_entities_with_or_without_bom(
    entities: list[str], has_byte_order_mark: bool
) -> None:
    prefix = UTF8_BYTE_ORDER_MARK if has_byte_order_mark else ""
    contents = prefix + entry_line(entities, REASON) + "\n"

    with tempfile.TemporaryDirectory() as directory:
        whitelist = Path(directory) / "whitelist.txt"
        whitelist.write_text(contents, encoding="utf-8")
        entries = read_whitelist(whitelist)

    key = (ANALYZED_PATH.resolve(), UNIT_KIND, UNIT_NAME)
    assert entries == {key: WhitelistEntry(tuple(entities), REASON)}


@given(sorted_entity_lists)
def test_parse_entry_property_keeps_the_exact_entities(
    entities: list[str],
) -> None:
    _, entry = parse_entry(entry_line(entities, REASON))

    assert entry.entities == tuple(entities)


@given(st.lists(entity_names, min_size=2, unique=True))
def test_parse_entities_property_accepts_only_sorted_lists(
    entities: list[str],
) -> None:
    if entities == sorted(entities):
        assert parse_entities(entities) == tuple(entities)
        return

    with pytest.raises(ValueError, match="sorted"):
        parse_entities(entities)


@given(sorted_entity_lists, sorted_entity_lists)
def test_apply_whitelist_property_suppresses_only_exact_entity_match(
    unit_entities: list[str], entry_entities: list[str]
) -> None:
    reports = single_unit_reports(unit_entities)
    key = (ANALYZED_PATH.resolve(), UNIT_KIND, UNIT_NAME)
    entries = {key: WhitelistEntry(tuple(entry_entities), REASON)}

    summary = apply_whitelist(reports, entries)

    is_exact_match = unit_entities == entry_entities
    assert reports[0]["units"][0]["whitelisted"] == is_exact_match
    assert summary["whitelisted_count"] == int(is_exact_match)


@given(unit_names.filter(lambda name: name != UNIT_NAME), st.booleans())
def test_reject_stale_entries_property_fails_only_for_analyzed_paths(
    entry_name: str, is_path_analyzed: bool
) -> None:
    path = ANALYZED_PATH if is_path_analyzed else UNANALYZED_PATH
    key = (path.resolve(), UNIT_KIND, entry_name)
    entries = {key: WhitelistEntry(("network",), REASON)}
    reports = single_unit_reports(["network"])

    if not is_path_analyzed:
        reject_stale_entries(reports, entries)
        return

    with pytest.raises(ValueError, match=entry_name):
        reject_stale_entries(reports, entries)
