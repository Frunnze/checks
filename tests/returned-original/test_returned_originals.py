import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "returned-original" / "python"
    / "returned_originals.py"
)
_COPIES = ("list({})", "dict({})", "{}.copy()", "{}[:]", "copy.deepcopy({})")
_CHANGES = ("{}[0] = 1", "{}.clear()", "del {}[0]", "{}.update(extra)")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "copies.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="copies.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _returned(
    line_number: int, original: str, copy: str, copy_line_number: int
) -> str:
    return (
        f"copies.py:{line_number}: returns {original} unchanged, but its"
        f" copy {copy} (line {copy_line_number}) was changed - return"
        f" {copy} instead"
    )


def test_reports_a_list_edited_through_its_copy(tmp_path: Path) -> None:
    source = (
        "def label(rows):\n"
        "    labelled = list(rows)\n"
        "    for index, row in enumerate(labelled):\n"
        "        if labelled[index] != row.upper():\n"
        "            labelled[index] = row.upper()\n"
        "    return rows\n"
    )

    assert _report_for(tmp_path, source) == [
        _returned(6, "rows", "labelled", 2)
    ]


def test_reports_every_kind_of_copy(tmp_path: Path) -> None:
    source = (
        "import copy\n"
        "def with_defaults(options):\n"
        "    merged: dict[str, int] = options.copy()\n"
        "    merged.setdefault('retries', 3)\n"
        "    return options\n"
        "def ordered(items):\n"
        "    sorted_items = items[:]\n"
        "    sorted_items.sort()\n"
        "    del sorted_items[0]\n"
        "    return items\n"
        "def trimmed(document):\n"
        "    edited = copy.deepcopy(document)\n"
        "    if len(edited) > 3:\n"
        "        edited.pop()\n"
        "    return document\n"
    )

    assert _report_for(tmp_path, source) == [
        _returned(5, "options", "merged", 3),
        _returned(10, "items", "sorted_items", 7),
        _returned(15, "document", "edited", 12),
    ]


def test_reports_only_the_returns_after_the_copy(tmp_path: Path) -> None:
    source = (
        "def normalized(values):\n"
        "    if not values:\n"
        "        return values\n"
        "    cleaned = set(values)\n"
        "    cleaned.discard(None)\n"
        "    return values\n"
    )

    assert _report_for(tmp_path, source) == [
        _returned(6, "values", "cleaned", 4)
    ]


def test_passes_a_function_that_returns_the_copy(tmp_path: Path) -> None:
    source = (
        "def label(rows):\n"
        "    labelled = list(rows)\n"
        "    labelled[0] = labelled[0].upper()\n"
        "    return labelled\n"
    )

    assert _report_for(tmp_path, source) == []


@pytest.mark.parametrize(
    "escape",
    [
        "store(labelled)",
        "self.saved = labelled",
        "results.append(labelled)",
        "callback = lambda: labelled",
        "add = labelled.append",
        "ordered = sorted(labelled)",
        "found = 'admin' in labelled",
        "missing = 'admin' not in labelled",
    ],
)
def test_passes_a_copy_that_is_used_elsewhere(
    tmp_path: Path, escape: str
) -> None:
    source = (
        "def label(self, rows, results):\n"
        "    labelled = list(rows)\n"
        "    labelled.append('admin')\n"
        f"    {escape}\n"
        "    return rows\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_copy_that_is_only_read(tmp_path: Path) -> None:
    source = (
        "def count(rows):\n"
        "    snapshot = list(rows)\n"
        "    for row in snapshot:\n"
        "        print(row, len(snapshot), snapshot[0])\n"
        "    return rows\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_an_original_that_is_changed_too(tmp_path: Path) -> None:
    source = (
        "def expand(frontier, discovered):\n"
        "    pending = set(frontier)\n"
        "    for node in discovered:\n"
        "        pending.discard(node)\n"
        "        frontier.add(node)\n"
        "    return frontier\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_an_original_bound_again_after_the_copy(
    tmp_path: Path,
) -> None:
    source = (
        "def drain(queue):\n"
        "    waiting = list(queue)\n"
        "    waiting.pop()\n"
        "    queue = refreshed(waiting[0])\n"
        "    return queue\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_copy_bound_to_the_same_name(tmp_path: Path) -> None:
    source = (
        "def label(rows):\n"
        "    rows = list(rows)\n"
        "    rows.append('admin')\n"
        "    return rows\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_call_that_is_not_a_plain_copy(tmp_path: Path) -> None:
    source = (
        "def with_defaults(options, base):\n"
        "    merged = dict(options, retries=3)\n"
        "    merged['timeout'] = 5\n"
        "    shown = list(base.rows)\n"
        "    shown.append(1)\n"
        "    window = options[1:]\n"
        "    window.clear()\n"
        "    return options\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_copy_changed_inside_a_nested_function(
    tmp_path: Path,
) -> None:
    source = (
        "def outer(rows):\n"
        "    def helper():\n"
        "        local = list(rows)\n"
        "        local.append(1)\n"
        "    helper()\n"
        "    return rows\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    copy_template=st.sampled_from(_COPIES),
    change_template=st.sampled_from(_CHANGES),
    returned=st.sampled_from(("original", "edited")),
)
def test_property_flags_only_a_returned_original(
    tmp_path: Path, copy_template: str, change_template: str, returned: str
) -> None:
    source = (
        "import copy\n"
        "def adjust(original, extra):\n"
        f"    edited = {copy_template.format('original')}\n"
        f"    {change_template.format('edited')}\n"
        f"    return {returned}\n"
    )

    expected = (
        [_returned(5, "original", "edited", 3)]
        if returned == "original"
        else []
    )

    assert _report_for(tmp_path, source) == expected
