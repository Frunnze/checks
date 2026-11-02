import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "discarded-result" / "python"
    / "discarded_results.py"
)
_FIX = "so assign the result or drop the call"
_TEXT_CALLS = {
    "replace": "replace('-', ' ')",
    "strip": "strip()",
    "lower": "lower()",
    "removeprefix": "removeprefix('#')",
    "split": "split(',')",
    "zfill": "zfill(4)",
}
_DISCARD_FORMS = ("", "_ = ")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "labels.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="labels.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _finding(line_number: int, call: str, reason: str) -> str:
    return (
        f"labels.py:{line_number}: the result of {call} is thrown away"
        f" - {reason}, {_FIX}"
    )


def test_reports_a_string_method_result_thrown_away(tmp_path: Path) -> None:
    source = (
        "def slug(title: str) -> str:\n"
        "    _ = title.replace(' ', '-')\n"
        "    title.lower()\n"
        "    return title\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(2, "title.replace()", "str values never change in place"),
        _finding(3, "title.lower()", "str values never change in place"),
    ]


def test_infers_strings_from_literals_and_chains(tmp_path: Path) -> None:
    source = (
        "GREETING = 'hello'\n"
        "def banner(raw: bytes | None, parts):\n"
        "    label = f'{parts[0]}!'\n"
        "    label.upper()\n"
        "    ', '.join(parts)\n"
        "    raw.strip().decode().title()\n"
        "    GREETING.capitalize()\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(4, "label.upper()", "str values never change in place"),
        _finding(5, "', '.join()", "str values never change in place"),
        _finding(
            6,
            "raw.strip().decode().title()",
            "str values never change in place",
        ),
        _finding(
            7, "GREETING.capitalize()", "str values never change in place"
        ),
    ]


def test_reports_dates_and_paths(tmp_path: Path) -> None:
    source = (
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        "class Report:\n"
        "    created: datetime\n"
        "    def save(self, root):\n"
        "        self.created.replace(tzinfo=timezone.utc)\n"
        "        stamp = datetime.now()\n"
        "        stamp.astimezone(timezone.utc)\n"
        "        target = Path(root) / 'report'\n"
        "        target.with_suffix('.txt')\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(
            6,
            "self.created.replace()",
            "datetime values never change in place",
        ),
        _finding(
            8, "stamp.astimezone()", "datetime values never change in place"
        ),
        _finding(
            10, "target.with_suffix()", "Path values never change in place"
        ),
    ]


def test_reports_pure_builtins(tmp_path: Path) -> None:
    source = (
        "def rank(scores, price):\n"
        "    sorted(scores)\n"
        "    _ = round(price, 2)\n"
        "    return scores, price\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(2, "sorted()", "sorted() changes nothing in place"),
        _finding(3, "round()", "round() changes nothing in place"),
    ]


def test_passes_mutable_and_unknown_receivers(tmp_path: Path) -> None:
    source = (
        "def tidy(document, items: list[str], cache):\n"
        "    document.replace('a', 'b')\n"
        "    _ = items.pop()\n"
        "    cache.update(document)\n"
        "    label = 'draft'\n"
        "    for label in document.labels:\n"
        "        pass\n"
        "    label.strip()\n"
        "    cleaned = document.title.strip()\n"
        "    return cleaned\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_calls_kept_for_the_error_they_raise(tmp_path: Path) -> None:
    source = (
        "import pytest\n"
        "from pathlib import Path\n"
        "def check(value: str, payload: bytes, upload: Path, root: Path):\n"
        "    try:\n"
        "        if value:\n"
        "            value.format(name='x')\n"
        "    except KeyError:\n"
        "        return False\n"
        "    with pytest.raises(ValueError):\n"
        "        sorted([value, 1])\n"
        "    int(value, 16)\n"
        "    float(value)\n"
        "    str(payload, 'utf-8')\n"
        "    payload.decode('ascii')\n"
        "    upload.relative_to(root)\n"
        "    upload.resolve(strict=True)\n"
        "    return True\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_shadowed_builtin(tmp_path: Path) -> None:
    source = (
        "from ordering import sorted\n"
        "def rank(scores):\n"
        "    sorted(scores)\n"
        "    def round(value):\n"
        "        return value\n"
        "    round(scores)\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    method=st.sampled_from(sorted(_TEXT_CALLS)),
    form=st.sampled_from(_DISCARD_FORMS),
)
def test_discard_property_flags_only_the_thrown_away_result(
    tmp_path: Path, method: str, form: str
) -> None:
    call = _TEXT_CALLS[method]
    source = (
        "def clean(note: str):\n"
        f"    kept = note.{call}\n"
        f"    {form}note.{call}\n"
        "    return kept\n"
    )

    report = _report_for(tmp_path, source)

    assert report == [
        _finding(3, f"note.{method}()", "str values never change in place")
    ]


def test_skips_tests_and_benchmarks(tmp_path: Path) -> None:
    source = "def test_abs(value):\n    abs(value)\n    sorted([2, 1])\n"
    folder = tmp_path / "benchmarks"
    folder.mkdir()
    _ = (folder / "bench_numbers.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="benchmarks/bench_numbers.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    assert finished.stdout == ""
