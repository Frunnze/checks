import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_DEEP_TERMS = 1000
_FINDER = (
    _CHECKS / "experimental" / "unit-mismatch" / "python"
    / "unit_mismatches.py"
)
_UNIT_SUFFIXES = {
    "ns": "ns",
    "ms": "ms",
    "seconds": "s",
    "minutes": "min",
    "hours": "h",
    "bytes": "B",
    "kb": "KB",
    "mb": "MB",
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


def test_reports_milliseconds_given_to_sleep(tmp_path: Path) -> None:
    source = (
        "import time\n"
        "def back_off(retry_delay_ms):\n"
        "    time.sleep(retry_delay_ms)\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:3: retry_delay_ms is in ms but time.sleep() is in s"
    ]


def test_reports_a_clock_in_seconds_minus_milliseconds(
    tmp_path: Path,
) -> None:
    source = (
        "import time\n"
        "def is_stale(created_at_ms, max_age_seconds):\n"
        "    return time.time() - created_at_ms > max_age_seconds\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:3: created_at_ms is in ms but time.time() is in s"
    ]


def test_reports_an_expiry_keyword_in_another_unit(tmp_path: Path) -> None:
    source = (
        "def remember(cache, key, ttl_ms):\n"
        "    cache.set(key, '1', ex=ttl_ms)\n"
        "    schedule(key, delay_seconds=ttl_ms)\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:2: ttl_ms is in ms but ex= is in s",
        "timing.py:3: ttl_ms is in ms but delay_seconds= is in s",
    ]


def test_reports_bytes_compared_with_megabytes(tmp_path: Path) -> None:
    source = (
        "def too_big(upload_bytes, max_upload_mb):\n"
        "    return upload_bytes > max_upload_mb\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:2: max_upload_mb is in MB but upload_bytes is in B"
    ]


def test_reports_a_result_in_another_unit(tmp_path: Path) -> None:
    source = (
        "def deadline_seconds(started_ms):\n"
        "    return started_ms + 500\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:2: started_ms + 500 is in ms but the result of"
        " deadline_seconds() is in s"
    ]


def test_knows_the_unit_of_common_driver_settings(tmp_path: Path) -> None:
    source = (
        "def options(keepalive_seconds, settings):\n"
        "    settings['lock_timeout'] = keepalive_seconds\n"
        "    return {\n"
        "        'tcp_user_timeout': keepalive_seconds,\n"
        "        'connect_timeout': keepalive_seconds,\n"
        "        'idle_ms': settings['retry_seconds'],\n"
        "    }\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:2: keepalive_seconds is in s but settings['lock_timeout']"
        " is in ms",
        "timing.py:4: keepalive_seconds is in s but 'tcp_user_timeout' is"
        " in ms",
        "timing.py:6: settings['retry_seconds'] is in s but 'idle_ms' is"
        " in ms",
    ]


def test_reads_camel_case_names(tmp_path: Path) -> None:
    source = (
        "def wait(timeoutMs, delaySeconds):\n"
        "    timeoutMs = delaySeconds\n"
    )

    assert _report_for(tmp_path, source) == [
        "timing.py:2: delaySeconds is in s but timeoutMs is in ms"
    ]


def test_passes_converted_values_and_rates(tmp_path: Path) -> None:
    source = (
        "import time\n"
        "def wait(delay_ms, chunk_bytes, elapsed_seconds):\n"
        "    timeout_seconds = delay_ms / 1000\n"
        "    time.sleep(delay_ms / 1000)\n"
        "    bytes_per_second = chunk_bytes / elapsed_seconds\n"
        "    if delay_ms >= MS_IN_SECONDS:\n        delay_ms = 0\n"
        "    return timeout_seconds + elapsed_seconds, bytes_per_second\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    suffixes=st.lists(
        st.sampled_from(sorted(_UNIT_SUFFIXES)),
        min_size=2,
        max_size=2,
        unique=True,
    )
)
def test_unit_property_flags_only_a_sum_of_two_units(
    tmp_path: Path, suffixes: list[str]
) -> None:
    first, second = suffixes
    source = (
        f"def total(start_{first}, extra_{first}, other_{second}):\n"
        f"    kept = start_{first} + extra_{first}\n"
        f"    return start_{first} + other_{second}\n"
    )

    report = _report_for(tmp_path, source)

    assert report == [
        f"timing.py:3: other_{second} is in {_UNIT_SUFFIXES[second]} but"
        f" start_{first} is in {_UNIT_SUFFIXES[first]}"
    ]


def test_survives_deeply_nested_code(tmp_path: Path) -> None:
    terms = " + ".join(f"term_{index}" for index in range(_DEEP_TERMS))
    source = f"def total():\n    return {terms}\n"

    assert _report_for(tmp_path, source) == []
