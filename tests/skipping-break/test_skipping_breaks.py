import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "skipping-break" / "python"
    / "skipping_breaks.py"
)
_SEEN = "was already seen"
_EXCLUDED = "is one of the excluded values"
_DEEP_TERMS = 1000
_GROWTHS = (
    "seen.append(item)",
    "seen.add(item)",
    "seen.extend([item])",
    "seen.update([item])",
    "seen.insert(0, item)",
    "seen.appendleft(item)",
    "seen.setdefault(item)",
    "seen[item] = True",
)


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


def _finding(line: int, item: str, reason: str) -> str:
    return (
        f"loops.py:{line}: break ends the whole loop when {item} {reason},"
        " so the items after it are never looked at - use continue to skip"
        " only this one"
    )


def test_reports_a_break_on_an_item_already_seen(tmp_path: Path) -> None:
    source = (
        "def unique_names(users):\n"
        "    seen = set()\n"
        "    names = []\n"
        "    for user in users:\n"
        "        if user.name in seen:\n"
        "            break\n"
        "        seen.add(user.name)\n"
        "        names.append(user.name)\n"
        "    return names\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(6, "user.name", _SEEN)
    ]


def test_reports_a_seen_test_inside_an_or(tmp_path: Path) -> None:
    source = (
        "def collect(rows):\n"
        "    kept = []\n"
        "    for row in rows:\n"
        "        if not row or row in kept:\n"
        "            break\n"
        "        kept.append(row)\n"
        "    return kept\n"
    )

    assert _report_for(tmp_path, source) == [_finding(5, "row", _SEEN)]


def test_reports_a_collection_grown_by_assignment(tmp_path: Path) -> None:
    source = (
        "def index_by_key(records):\n"
        "    by_key = {}\n"
        "    for record in records:\n"
        "        key = record['key']\n"
        "        if key in by_key:\n"
        "            break\n"
        "        by_key[key] = record\n"
        "    return by_key\n"
    )

    assert _report_for(tmp_path, source) == [_finding(6, "key", _SEEN)]


def test_reports_a_break_on_excluded_values(tmp_path: Path) -> None:
    source = (
        "def accent(colors, darkest, lightest):\n"
        "    for candidate in colors:\n"
        "        if candidate['id'] in (darkest['id'], lightest['id']):\n"
        "            break\n"
        "        return candidate\n"
        "    return None\n"
        "async def pages(client, start, stop):\n"
        "    found = []\n"
        "    async for page in client.pages():\n"
        "        if page.number in [start, stop]:\n"
        "            break\n"
        "        found.append(page)\n"
        "    return found\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(4, "candidate['id']", _EXCLUDED),
        _finding(11, "page.number", _EXCLUDED),
    ]


def test_reports_values_from_enclosing_functions(tmp_path: Path) -> None:
    source = (
        "def make_filter(items, first):\n"
        "    def pick(second):\n"
        "        for item in items:\n"
        "            if item in (first, second):\n"
        "                break\n"
        "            yield item\n"
        "    return pick\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(5, "item", _EXCLUDED)
    ]


def test_reads_deeply_nested_code(tmp_path: Path) -> None:
    terms = " + ".join(["1"] * _DEEP_TERMS)
    source = (
        f"TOTAL = {terms}\n"
        "def unique(items):\n"
        "    seen = set()\n"
        "    for item in items:\n"
        "        if item in seen:\n"
        "            break\n"
        "        seen.add(item)\n"
    )

    assert _report_for(tmp_path, source) == [_finding(6, "item", _SEEN)]


def test_passes_skips_and_final_breaks(tmp_path: Path) -> None:
    source = (
        "def unique(items, first, second):\n"
        "    seen = set()\n"
        "    for item in items:\n"
        "        if item in seen or item in (first, second):\n"
        "            continue\n"
        "        seen.add(item)\n"
        "    for item in items:\n"
        "        seen.add(item)\n"
        "        if item in seen:\n"
        "            break\n"
        "    return seen\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_break_with_more_to_do(tmp_path: Path) -> None:
    source = (
        "def unique(items, log):\n"
        "    seen = set()\n"
        "    for item in items:\n"
        "        if item in seen:\n"
        "            log(item)\n"
        "            break\n"
        "        if item in seen:\n"
        "            break\n"
        "        else:\n"
        "            seen.add(item)\n"
        "        log(item)\n"
        "    return seen\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_stop_list_the_loop_does_not_grow(tmp_path: Path) -> None:
    source = (
        "def until_stop(words, stop_words):\n"
        "    kept = []\n"
        "    for word in words:\n"
        "        if word in stop_words:\n"
        "            break\n"
        "        kept.append(word)\n"
        "    return kept\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_stop_values_that_are_not_all_local(tmp_path: Path) -> None:
    source = (
        "def leading(parameters, first, rest):\n"
        "    kept = []\n"
        "    for parameter in parameters:\n"
        "        if parameter.kind in (VAR_KEYWORD, KEYWORD_ONLY):\n"
        "            break\n"
        "        if parameter.name in (first, 'end'):\n"
        "            break\n"
        "        if parameter.name in (first, SENTINEL):\n"
        "            break\n"
        "        if parameter.name in (first,):\n"
        "            break\n"
        "        if parameter.name in (first, *rest):\n"
        "            break\n"
        "        kept.append(parameter)\n"
        "    return kept\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_other_tests(tmp_path: Path) -> None:
    source = (
        "def unique(items, first, second, ready):\n"
        "    seen = set()\n"
        "    for item in items:\n"
        "        if ready and item in seen:\n"
        "            break\n"
        "        if item not in (first, second):\n"
        "            break\n"
        "        seen.add(item)\n"
        "    return seen\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_loops_outside_functions_and_while_loops(
    tmp_path: Path,
) -> None:
    source = (
        "seen = set()\n"
        "for item in ITEMS:\n"
        "    if item in seen:\n"
        "        break\n"
        "    seen.add(item)\n"
        "def drain(queue, seen):\n"
        "    while queue:\n"
        "        item = queue.pop()\n"
        "        if item in seen:\n"
        "            break\n"
        "        seen.add(item)\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    growth=st.sampled_from(_GROWTHS),
    keyword=st.sampled_from(("break", "continue")),
)
def test_break_property_flags_only_a_break(
    tmp_path: Path, growth: str, keyword: str
) -> None:
    source = (
        "def unique(items, seen):\n"
        "    for item in items:\n"
        "        if item in seen:\n"
        f"            {keyword}\n"
        f"        {growth}\n"
        "    return seen\n"
    )

    report = _report_for(tmp_path, source)

    expected = [_finding(4, "item", _SEEN)]
    assert report == (expected if keyword == "break" else [])
