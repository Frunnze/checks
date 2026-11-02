import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "page-probe" / "python" / "page_probes.py"
)


def _report_for(tmp_path: Path, modules: dict[str, str]) -> list[str]:
    for name, source in modules.items():
        _ = (tmp_path / name).write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(modules),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_a_probe_in_the_same_function(tmp_path: Path) -> None:
    source = (
        "def page(repository, owner, page_size):\n"
        "    items = repository.find(owner, page_size=page_size)\n"
        "    has_more = len(items) > page_size\n"
        "    return items[:page_size], has_more\n"
    )

    assert _report_for(tmp_path, {"paging.py": source}) == [
        "paging.py:2: items holds at most page_size items, so len(items) >"
        " page_size on line 3 is never true - fetch page_size + 1 to see"
        " whether more exist"
    ]


def test_reports_a_probe_in_a_helper_of_another_module(
    tmp_path: Path,
) -> None:
    endpoint = (
        "class Orders:\n"
        "    async def list(self, per_page):\n"
        "        found = await self._store.select(\n"
        "            per_page=per_page,\n"
        "        )\n"
        "        return self.paged(found, per_page)\n"
    )
    helper = (
        "class Pages:\n"
        "    def paged(self, records, size):\n"
        "        more = size < len(records)\n"
        "        return records[:size], more\n"
    )

    report = _report_for(
        tmp_path, {"orders.py": endpoint, "pages.py": helper}
    )

    assert report == [
        "orders.py:4: found holds at most per_page items, so size <"
        " len(records) in paged() is never true - fetch per_page + 1 to"
        " see whether more exist"
    ]


def test_reports_a_positional_count_and_a_shifted_threshold(
    tmp_path: Path,
) -> None:
    source = (
        "def drain(queue, count):\n"
        "    batch = queue.take(count)\n"
        "    if len(batch) >= count + 1:\n"
        "        queue.schedule()\n"
        "    return batch\n"
    )

    assert _report_for(tmp_path, {"paging.py": source}) == [
        "paging.py:2: batch holds at most count items, so len(batch) >="
        " count + 1 on line 3 is never true - fetch count + 1 to see"
        " whether more exist"
    ]


def test_passes_look_ahead_rows_full_pages_and_splits(
    tmp_path: Path,
) -> None:
    source = (
        "def page(repository, limit):\n"
        "    rows = repository.find(limit=limit + 1)\n"
        "    return rows[:limit], len(rows) > limit\n"
        "def full(repository, limit):\n"
        "    rows = repository.find(limit=limit)\n"
        "    return rows, len(rows) >= limit\n"
        "def fields(line, count):\n"
        "    parts = line.split(',', count)\n"
        "    return len(parts) > count\n"
    )

    assert _report_for(tmp_path, {"paging.py": source}) == []


def test_passes_names_that_change_between_fetch_and_test(
    tmp_path: Path,
) -> None:
    source = (
        "def grown(repository, limit):\n"
        "    rows = repository.find(limit=limit)\n"
        "    limit -= 1\n"
        "    return len(rows) > limit\n"
        "def refilled(repository, other, limit):\n"
        "    rows = repository.find(limit=limit)\n"
        "    rows = other.find(limit=limit + 1)\n"
        "    return len(rows) > limit\n"
        "def early(repository, rows, limit):\n"
        "    more = len(rows) > limit\n"
        "    rows = repository.find(limit=limit)\n"
        "    return more\n"
    )

    assert _report_for(tmp_path, {"paging.py": source}) == []


def test_passes_helpers_it_cannot_resolve_or_map(tmp_path: Path) -> None:
    source = (
        "def page(repository, limit, offset):\n"
        "    rows = repository.find(limit=limit)\n"
        "    shown = summarize(rows, offset)\n"
        "    return render(rows, limit=limit), shown\n"
        "def render(rows, limit):\n"
        "    return len(rows) > limit\n"
        "def summarize(rows, offset):\n"
        "    return len(rows) > offset\n"
    )
    other = (
        "def render(rows, limit):\n"
        "    return len(rows) > limit\n"
    )

    report = _report_for(tmp_path, {"paging.py": source, "other.py": other})

    assert report == []


@HYPOTHESIS_SETTINGS
@given(
    fetched_extra=st.integers(min_value=0, max_value=2),
    threshold_extra=st.integers(min_value=0, max_value=2),
    is_strict=st.booleans(),
)
def test_probe_property_flags_only_an_unreachable_count(
    tmp_path: Path, fetched_extra: int, threshold_extra: int, is_strict: bool
) -> None:
    fetched = f"limit + {fetched_extra}" if fetched_extra else "limit"
    threshold = f"limit + {threshold_extra}" if threshold_extra else "limit"
    operator = ">" if is_strict else ">="
    source = (
        "def page(repository, limit):\n"
        f"    rows = repository.find(limit={fetched})\n"
        f"    return len(rows) {operator} {threshold}\n"
    )
    needed_extra = threshold_extra + int(is_strict)
    needed = f"limit + {needed_extra}" if needed_extra else "limit"
    expected = [
        f"paging.py:2: rows holds at most {fetched} items, so len(rows)"
        f" {operator} {threshold} on line 3 is never true - fetch"
        f" {needed} to see whether more exist"
    ]

    report = _report_for(tmp_path, {"paging.py": source})

    assert report == (expected if fetched_extra < needed_extra else [])
