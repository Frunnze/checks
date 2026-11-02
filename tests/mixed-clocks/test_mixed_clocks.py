import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "mixed-clocks" / "python" / "mixed_clocks.py"
)
_ADVICE = " - read both from the same clock"
_CLOCK_READINGS = {
    "time.time()": "wall",
    "time.time_ns()": "wall",
    "datetime.datetime.now().timestamp()": "wall",
    "time.monotonic()": "monotonic",
    "time.monotonic_ns()": "monotonic",
    "asyncio.get_running_loop().time()": "monotonic",
    "time.perf_counter()": "perf_counter",
    "time.process_time()": "process_time",
}


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "timing.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="timing.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_a_wall_deadline_checked_against_monotonic(
    tmp_path: Path,
) -> None:
    source = (
        "import time\n"
        "def wait_for(job, timeout_seconds):\n"
        "    deadline = time.time() + timeout_seconds\n"
        "    while not job.done() and time.monotonic() < deadline:\n"
        "        time.sleep(0.1)\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:4: time.monotonic() is on the monotonic clock but"
        " deadline (set on line 3) is on the wall clock" + _ADVICE
    ]


def test_reports_an_event_loop_time_minus_a_wall_start(
    tmp_path: Path,
) -> None:
    source = (
        "import asyncio\n"
        "import time\n"
        "async def measure(step):\n"
        "    loop = asyncio.get_running_loop()\n"
        "    started = time.time()\n"
        "    await step()\n"
        "    return loop.time() - started\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:7: loop.time() is on the monotonic clock but"
        " started (set on line 5) is on the wall clock" + _ADVICE
    ]


def test_reports_an_attribute_set_from_another_clock(
    tmp_path: Path,
) -> None:
    source = (
        "import time\n"
        "class Lease:\n"
        "    def __init__(self, seconds):\n"
        "        self._expires = time.perf_counter() + seconds\n"
        "    def expired(self):\n"
        "        return time.monotonic() >= self._expires\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:6: time.monotonic() is on the monotonic clock but"
        " self._expires (set on line 4) is on the perf_counter clock"
        + _ADVICE
    ]


def test_follows_imported_names_and_datetime_stamps(tmp_path: Path) -> None:
    source = (
        "from datetime import datetime\n"
        "from time import monotonic as now\n"
        "CREATED = datetime.now().timestamp()\n"
        "def age():\n"
        "    return now() - CREATED\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:5: now() is on the monotonic clock but CREATED"
        " (set on line 3) is on the wall clock" + _ADVICE
    ]


def test_knows_a_loop_from_its_annotation(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "import time\n"
        "def overdue(loop: asyncio.AbstractEventLoop, started):\n"
        "    limit = time.time() + 30\n"
        "    return loop.time() > limit\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:5: loop.time() is on the monotonic clock but limit"
        " (set on line 4) is on the wall clock" + _ADVICE
    ]


def test_passes_deadlines_and_durations_on_one_clock(
    tmp_path: Path,
) -> None:
    source = (
        "import time\n"
        "class Poller:\n"
        "    def __init__(self):\n"
        "        self._started = time.monotonic()\n"
        "    def run(self, job, timeout_seconds):\n"
        "        deadline = time.monotonic() + timeout_seconds\n"
        "        while time.monotonic() < deadline:\n"
        "            job.poll()\n"
        "        took = time.perf_counter()\n"
        "        took = time.perf_counter() - took\n"
        "        return time.monotonic() - self._started, took\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_deliberate_conversions_between_clocks(
    tmp_path: Path,
) -> None:
    source = (
        "import time\n"
        "def wall_start(started_monotonic):\n"
        "    offset = time.time() - time.monotonic()\n"
        "    elapsed = time.monotonic() - started_monotonic\n"
        "    started_wall = time.time() - elapsed\n"
        "    shifted = started_monotonic + offset\n"
        "    return time.time() > shifted, started_wall\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_names_whose_clock_is_unknown(tmp_path: Path) -> None:
    source = (
        "import time\n"
        "def expired(deadline, started, use_wall):\n"
        "    now = time.time() if use_wall else time.monotonic()\n"
        "    mark = time.time()\n"
        "    mark = time.monotonic()\n"
        "    left = deadline - time.monotonic()\n"
        "    return now > started, time.time() > mark, left < time.time()\n"
    )

    assert _report_for(tmp_path, source) == []


def test_keeps_scopes_apart(tmp_path: Path) -> None:
    source = (
        "import time\n"
        "def start():\n"
        "    begun = time.time()\n"
        "    return begun\n"
        "def finish(begun):\n"
        "    return time.monotonic() - begun\n"
        "class Other:\n"
        "    def mark(self):\n"
        "        self.at = time.time()\n"
        "def unrelated(item):\n"
        "    return time.monotonic() - item.at\n"
        "class Settings:\n"
        "    loaded = time.time()\n"
        "def since_load():\n"
        "    return time.monotonic() - loaded\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    readings=st.lists(
        st.sampled_from(sorted(_CLOCK_READINGS)),
        min_size=2,
        max_size=2,
    )
)
def test_clock_property_flags_only_two_different_clocks(
    tmp_path: Path, readings: list[str]
) -> None:
    first, second = readings
    source = (
        "import asyncio\n"
        "import datetime\n"
        "import time\n"
        "async def timed_out(wait_seconds):\n"
        f"    mark = {first} + wait_seconds\n"
        f"    return {second} > mark\n"
    )
    first_clock = _CLOCK_READINGS[first]
    second_clock = _CLOCK_READINGS[second]
    expected = [
        f"timing.py:6: {second} is on the {second_clock} clock but mark"
        f" (set on line 5) is on the {first_clock} clock" + _ADVICE
    ]

    report = _report_for(tmp_path, source)

    assert report == (expected if first_clock != second_clock else [])
