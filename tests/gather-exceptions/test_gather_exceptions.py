import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "gather-exceptions" / "python"
    / "gather_exceptions.py"
)
_KEYWORDS = {
    "": "raises",
    ", return_exceptions=False": "raises",
    ", return_exceptions=True": "returns",
    ", return_exceptions=keep": "unknown",
    ", **options": "unknown",
}
_TESTED_TYPES = [
    "Exception",
    "BaseException",
    "(ValueError, Exception)",
    "(Exception, CancelledError)",
]


def _report_for(tmp_path: Path, sources: dict[str, str]) -> list[str]:
    for name, source in sources.items():
        _ = (tmp_path / name).write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(sources),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _typed(line_number: int, name: str) -> str:
    return (
        f"fetching.py:{line_number}: {name} is typed to hold exceptions,"
        " but gather without return_exceptions=True raises the first one"
        " instead of returning it - pass return_exceptions=True or drop the"
        " exception from the type"
    )


def _narrow(line_number: int, name: str) -> str:
    return (
        f"fetching.py:{line_number}: {name} comes from"
        " gather(return_exceptions=True), which also returns BaseException"
        " such as CancelledError, and testing only Exception passes it on"
        " as a result - test BaseException instead"
    )


def test_reports_a_result_typed_to_hold_exceptions(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def fetch_all(urls):\n"
        "    pages: list[str | Exception] = await asyncio.gather(\n"
        "        *[fetch(url) for url in urls], return_exceptions=False\n"
        "    )\n"
        "    return pages\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == [
        _typed(3, "pages")
    ]


def test_reports_a_type_alias_from_another_file(tmp_path: Path) -> None:
    outcomes = (
        "from typing import TypeAlias\n"
        "type Failure = BaseException\n"
        "Outcome: TypeAlias = 'tuple[str, bytes] | Failure'\n"
    )
    source = (
        "from asyncio import gather\n"
        "async def fetch_all(jobs):\n"
        "    outcomes: list[Outcome] = await gather(*jobs)\n"
        "    later: 'list[Outcome]' = await gather(*jobs)\n"
        "    return outcomes, later\n"
    )

    report = _report_for(
        tmp_path, {"outcomes.py": outcomes, "fetching.py": source}
    )

    assert report == [_typed(3, "outcomes"), _typed(4, "later")]


def test_reports_a_result_used_on_the_else_branch(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def fetch_all(jobs):\n"
        "    results = await asyncio.gather(*jobs, return_exceptions=True)\n"
        "    for job, result in zip(jobs, results):\n"
        "        if isinstance(result, Exception):\n"
        "            log(job, result)\n"
        "        else:\n"
        "            store(result)\n"
        "async def fetch_some(jobs):\n"
        "    replies = await asyncio.gather(*jobs, return_exceptions=True)\n"
        "    for index, reply in enumerate(replies):\n"
        "        if not isinstance(reply, Exception):\n"
        "            store(index, reply)\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == [
        _narrow(5, "results"),
        _narrow(12, "replies"),
    ]


def test_reports_a_result_used_after_an_early_exit(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def fetch_all(jobs):\n"
        "    replies = await asyncio.gather(*jobs, return_exceptions=True)\n"
        "    for reply in replies:\n"
        "        if isinstance(reply, Exception):\n"
        "            log(reply)\n"
        "            continue\n"
        "        store(reply)\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == [
        _narrow(5, "replies")
    ]


def test_reports_a_filter_that_keeps_the_rest(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def fetch_all(jobs):\n"
        "    pages = await asyncio.gather(*jobs, return_exceptions=True)\n"
        "    return [\n"
        "        page for page in pages\n"
        "        if not isinstance(page, Exception)\n"
        "    ]\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == [
        _narrow(6, "pages")
    ]


def test_passes_handlers_that_only_log_exceptions(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def close_all(jobs):\n"
        "    results = await asyncio.gather(*jobs, return_exceptions=True)\n"
        "    for result in results:\n"
        "        if isinstance(result, Exception):\n"
        "            log(result)\n"
        "    for result in results:\n"
        "        if isinstance(result, Exception):\n"
        "            raise result\n"
        "    for result in results:\n"
        "        if isinstance(result, Exception):\n"
        "            log(result)\n"
        "        count(result)\n"
        "    return len(results)\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == []


def test_passes_exception_values_from_raising_gather(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def finish(managers, outputs):\n"
        "    await asyncio.gather(*(m.start() for m in managers))\n"
        "    ends = await asyncio.gather(*(run(o) for o in outputs))\n"
        "    for manager, end in zip(managers, ends):\n"
        "        if isinstance(end, Exception):\n"
        "            manager.fail(end)\n"
        "        else:\n"
        "            manager.end(end)\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == []


def test_passes_returned_exceptions_handled_in_full(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def fetch_all(jobs):\n"
        "    results: list[str | BaseException] = await asyncio.gather(\n"
        "        *jobs, return_exceptions=True\n"
        "    )\n"
        "    kept = [r for r in results if not isinstance(r, BaseException)]\n"
        "    for result in results:\n"
        "        if isinstance(result, (Exception, CancelledError)):\n"
        "            log(result)\n"
        "        else:\n"
        "            store(result)\n"
        "    return kept\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == []


def test_passes_a_return_exceptions_it_cannot_read(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def fetch_all(jobs, keep, options):\n"
        "    kept = await asyncio.gather(*jobs, return_exceptions=keep)\n"
        "    passed: list[str | Exception] = await asyncio.gather(\n"
        "        *jobs, **options\n"
        "    )\n"
        "    for result in kept:\n"
        "        if not isinstance(result, Exception):\n"
        "            store(result)\n"
        "    return passed\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == []


def test_passes_results_typed_without_exceptions(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "Outcome = str | Exception\n"
        "Fallback: type = Exception\n"
        "async def fetch_all(jobs):\n"
        "    pages: list[str] = await asyncio.gather(*jobs)\n"
        "    outcomes: list[Outcome] = await asyncio.gather(*jobs)\n"
        "    fallbacks: list[Fallback] = await asyncio.gather(*jobs)\n"
        "    waited: list[str | Exception] = await asyncio.wait(jobs)\n"
        "    return pages, outcomes, fallbacks, waited\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == []


def test_passes_names_not_bound_to_a_result(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "async def finish(jobs, outputs, first_job, second_job):\n"
        "    managers = await asyncio.gather(*jobs, return_exceptions=True)\n"
        "    for manager, output in zip(managers, outputs):\n"
        "        if not isinstance(output, Exception):\n"
        "            manager.end(output)\n"
        "    for position, job in enumerate(managers):\n"
        "        if not isinstance(position, Exception):\n"
        "            log(position, job)\n"
        "    first, second = await asyncio.gather(\n"
        "        first_job, second_job, return_exceptions=True\n"
        "    )\n"
        "    if not isinstance(first, Exception):\n"
        "        store(first, second)\n"
    )

    assert _report_for(tmp_path, {"fetching.py": source}) == []


@HYPOTHESIS_SETTINGS
@given(
    keyword=st.sampled_from(sorted(_KEYWORDS)),
    tested_types=st.sampled_from(_TESTED_TYPES),
    name=st.sampled_from(["results", "pages", "replies"]),
    is_stored=st.booleans(),
)
def test_gather_property_flags_only_a_result_that_slips_through(
    tmp_path: Path,
    keyword: str,
    tested_types: str,
    name: str,
    *,
    is_stored: bool,
) -> None:
    handled = "        else:\n            store(item)\n" if is_stored else ""
    source = (
        "import asyncio\n"
        "async def fetch_all(jobs, keep, options):\n"
        f"    {name} = await asyncio.gather(*jobs{keyword})\n"
        f"    for item in {name}:\n"
        f"        if isinstance(item, {tested_types}):\n"
        "            log(item)\n"
        f"{handled}"
    )
    slips_through = (
        _KEYWORDS[keyword] == "returns"
        and tested_types == "Exception"
        and is_stored
    )
    expected = [_narrow(5, name)] if slips_through else []

    assert _report_for(tmp_path, {"fetching.py": source}) == expected
