import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "lost-loop-update" / "python"
    / "lost_loop_updates.py"
)
_EMPTY_COLLECTIONS = ("[]", "{}", "()", "set()", "list()", "dict()")
_NAMES = ("rows", "found", "collected_items", "totals")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "loops.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="loops.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _replaced(line_number: int, name: str) -> str:
    return (
        f"loops.py:{line_number}: {name} is replaced on every pass, so only"
        f" the last is kept - add to {name} instead of replacing it"
    )


def _rebuilt(line_number: int, name: str, source: str) -> str:
    return (
        f"loops.py:{line_number}: {name} is rebuilt from {source} on every"
        " pass, so the changes of earlier passes are lost - build on"
        f" {name} instead"
    )


def test_reports_a_collected_list_replaced_on_every_pass(
    tmp_path: Path,
) -> None:
    source = (
        "def collect(pages):\n"
        "    items = []\n"
        "    for page in pages:\n"
        "        if page is None:\n"
        "            continue\n"
        "        items = page.items()\n"
        "    return items\n"
    )

    assert _report_for(tmp_path, source) == [_replaced(6, "items")]


def test_reports_a_replacement_in_a_while_loop(tmp_path: Path) -> None:
    source = (
        "def drain(queue):\n"
        "    latest: dict[str, int] = {}\n"
        "    while queue.pending():\n"
        "        latest: dict[str, int] = queue.next_batch()\n"
        "    return latest\n"
    )

    assert _report_for(tmp_path, source) == [_replaced(4, "latest")]


def test_reports_a_replacement_in_an_async_loop(tmp_path: Path) -> None:
    source = (
        "async def gather(stream):\n"
        "    seen = set()\n"
        "    async for chunk in stream:\n"
        "        seen = chunk.keys()\n"
        "    print(len(seen))\n"
    )

    assert _report_for(tmp_path, source) == [_replaced(4, "seen")]


def test_reports_a_copy_rebuilt_from_its_source(tmp_path: Path) -> None:
    source = (
        "def apply(current, updates):\n"
        "    existing = list(current or [])\n"
        "    for update in updates:\n"
        "        if update.removed is None:\n"
        "            existing.append(update)\n"
        "        else:\n"
        "            existing = without(current or [], update.removed)\n"
        "    return existing\n"
    )

    assert _report_for(tmp_path, source) == [
        _rebuilt(7, "existing", "current or []")
    ]


def test_reports_rebuilt_copies_of_every_kind(tmp_path: Path) -> None:
    source = (
        "def settle(defaults, pending, scores, changes):\n"
        "    merged = dict(defaults)\n"
        "    for key, value in changes:\n"
        "        merged[key] = value\n"
        "        merged = drop_empty(defaults)\n"
        "    remaining = pending.copy()\n"
        "    for task in changes:\n"
        "        remaining.discard(task)\n"
        "        remaining = pending - {task}\n"
        "    ranked = sorted(scores, key=abs)\n"
        "    for score in changes:\n"
        "        ranked.remove(score)\n"
        "        ranked = top(scores)\n"
        "    return merged, remaining, ranked\n"
    )

    assert _report_for(tmp_path, source) == [
        _rebuilt(5, "merged", "defaults"),
        _rebuilt(9, "remaining", "pending"),
        _rebuilt(13, "ranked", "scores"),
    ]


def test_passes_a_value_that_builds_on_itself(tmp_path: Path) -> None:
    source = (
        "def collect(pages, current):\n"
        "    items = []\n"
        "    for page in pages:\n"
        "        items = items + page.items()\n"
        "    existing = list(current)\n"
        "    for page in pages:\n"
        "        existing.append(page)\n"
        "        existing = trimmed(existing, current)\n"
        "    return items, existing\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_loop_that_reads_the_previous_value(
    tmp_path: Path,
) -> None:
    source = (
        "def changes(rows):\n"
        "    previous = []\n"
        "    for row in rows:\n"
        "        report(row, previous)\n"
        "        previous = row.cells()\n"
        "    return previous\n"
    )

    assert _report_for(tmp_path, source) == []


@pytest.mark.parametrize(
    "leave", ["break", "return None", "raise StopIteration", "yield group"]
)
def test_passes_a_loop_that_can_stop_early(
    tmp_path: Path, leave: str
) -> None:
    source = (
        "def first_full(groups):\n"
        "    items = []\n"
        "    for group in groups:\n"
        "        items = group.members()\n"
        "        if len(group) > 3:\n"
        f"            {leave}\n"
        "    return items\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_conditional_last_match(tmp_path: Path) -> None:
    source = (
        "def best(candidates, limit):\n"
        "    chosen = []\n"
        "    for candidate in candidates:\n"
        "        if candidate.score > limit:\n"
        "            chosen = candidate.items()\n"
        "    return chosen\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_start_that_is_not_an_empty_collection(
    tmp_path: Path,
) -> None:
    source = (
        "def last(pages, fallback):\n"
        "    latest = None\n"
        "    for page in pages:\n"
        "        latest = page.items()\n"
        "    newest = [fallback]\n"
        "    for page in pages:\n"
        "        newest = page.items()\n"
        "    return latest, newest\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_reset_to_an_empty_collection(tmp_path: Path) -> None:
    source = (
        "def reset(attempts):\n"
        "    pending = []\n"
        "    for attempt in attempts:\n"
        "        pending = list()\n"
        "    return pending\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_value_never_read_after_the_loop(tmp_path: Path) -> None:
    source = (
        "def show(pages):\n"
        "    items = []\n"
        "    for page in pages:\n"
        "        items = page.items()\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_value_read_before_the_loop(tmp_path: Path) -> None:
    source = (
        "def watch(pages):\n"
        "    items = []\n"
        "    register(items)\n"
        "    for page in pages:\n"
        "        items = page.items()\n"
        "    return items\n"
    )

    assert _report_for(tmp_path, source) == []


def test_checks_only_the_first_loop_after_the_start(tmp_path: Path) -> None:
    source = (
        "def merge(first, second):\n"
        "    items = []\n"
        "    for page in first:\n"
        "        items.append(page)\n"
        "    for page in second:\n"
        "        items = page.items()\n"
        "    return items\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_copy_rebuilt_without_its_source(tmp_path: Path) -> None:
    source = (
        "def refresh(current, updates, base):\n"
        "    existing = list(current)\n"
        "    for update in updates:\n"
        "        existing.append(update)\n"
        "        existing = fetch_latest()\n"
        "    latest = dict(base)\n"
        "    for update in updates:\n"
        "        latest = merge(base, update)\n"
        "    return existing, latest\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_copy_of_a_source_that_the_loop_rebinds(
    tmp_path: Path,
) -> None:
    source = (
        "def iterate(state, steps):\n"
        "    best = state.copy()\n"
        "    for step in steps:\n"
        "        best.update(step.hints)\n"
        "        state = step.apply(state)\n"
        "        best = state.copy()\n"
        "    return best\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_copy_of_something_other_than_a_name(
    tmp_path: Path,
) -> None:
    source = (
        "def settle(config, changes):\n"
        "    merged = dict(config.defaults)\n"
        "    for key, value in changes:\n"
        "        merged[key] = value\n"
        "        merged = dict(config.defaults)\n"
        "    return merged\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_name_bound_inside_a_nested_function(
    tmp_path: Path,
) -> None:
    source = (
        "def settle(defaults, changes):\n"
        "    merged = dict(defaults)\n"
        "    for key, value in changes:\n"
        "        merged[key] = value\n"
        "        def restart():\n"
        "            merged = dict(defaults)\n"
        "            return merged\n"
        "        schedule(restart)\n"
        "    return merged\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    empty=st.sampled_from(_EMPTY_COLLECTIONS),
    name=st.sampled_from(_NAMES),
    replaces=st.booleans(),
)
def test_property_flags_only_a_replacing_pass(
    tmp_path: Path, empty: str, name: str, replaces: bool
) -> None:
    update = "batch.rows()" if replaces else f"{name} + batch.rows()"
    source = (
        "def collect(batches):\n"
        f"    {name} = {empty}\n"
        "    for batch in batches:\n"
        f"        {name} = {update}\n"
        f"    return {name}\n"
    )

    expected = [_replaced(4, name)] if replaces else []

    assert _report_for(tmp_path, source) == expected
