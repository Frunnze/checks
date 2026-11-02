import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "catastrophic-regex" / "python" / "catastrophic_regexes.py"
)
_SLOW = (
    "nests repeats that can split one text many ways, so a long"
    " non-matching input backtracks for ages"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "patterns.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="patterns.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_the_classic_nested_repeats(tmp_path: Path) -> None:
    source = (
        "import re\n"
        "WORDS = r'^(\\w+\\s?)*$'\n"
        "def check(text):\n"
        "    re.search(r'(a+)+b', text)\n"
        "    return re.match(WORDS, text)\n"
    )

    assert _report_for(tmp_path, source) == [
        f"patterns.py:4: '(a+)+b' {_SLOW}",
        f"patterns.py:5: '^(\\\\w+\\\\s?)*$' {_SLOW}",
    ]


def test_reports_overlapping_parts_inside_a_group(tmp_path: Path) -> None:
    source = (
        "import re\n"
        "TAG = re.compile(r'<tag(\\s+[^>]*)*>')\n"
        "MAIL = re.compile(r'^([a-z0-9]+\\.?)+@example\\.com$')\n"
    )

    assert _report_for(tmp_path, source) == [
        f"patterns.py:2: '<tag(\\\\s+[^>]*)*>' {_SLOW}",
        f"patterns.py:3: '^([a-z0-9]+\\\\.?)+@example\\\\.com$' {_SLOW}",
    ]


def test_passes_repeats_kept_apart_by_a_separator(tmp_path: Path) -> None:
    source = (
        "import re\n"
        "LIST = re.compile(r'^(\\d+,)*\\d+$')\n"
        "NAME = re.compile(r'^\\w+(\\.\\w+)*$')\n"
        "TAG = re.compile(r'<tag\\b[^>]*>')\n"
        "BAD = re.compile(r'(unclosed')\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    inner=st.sampled_from(["a+", "\\w+", "\\d*", "[a-z]+", ".+"]),
    outer=st.sampled_from(["*", "+", "{1,}", "{2,}"]),
)
def test_nesting_property_flags_every_unbounded_pair(
    tmp_path: Path, inner: str, outer: str
) -> None:
    pattern = f"({inner}){outer}!"
    source = (
        f"import re\nre.compile(r'{pattern}')\n"
        f"re.compile(r'({inner})!')\n"
    )

    report = _report_for(tmp_path, source)

    assert report == [f"patterns.py:2: {pattern!r} {_SLOW}"]
