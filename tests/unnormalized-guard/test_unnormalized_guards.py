import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "unnormalized-guard" / "python"
    / "unnormalized_guards.py"
)
_STRIPPING_METHODS = ("strip", "lstrip", "rstrip")
_EMPTINESS_TESTS = ("not {}", "{} == ''", "len({}) == 0")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "names.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="names.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _stripped(line: int, raw: str, assignment: str) -> str:
    normalized = assignment.split(" = ", maxsplit=1)[0]

    return (
        f"names.py:{line}: the guard tests {raw} for emptiness but the code"
        f" goes on with {assignment} - a whitespace-only {raw} passes; test"
        f" {normalized} instead"
    )


def _folded(line: int, raw: str, casing: str, assignment: str) -> str:
    normalized = assignment.split(" = ", maxsplit=1)[0]

    return (
        f"names.py:{line}: the guard compares {raw} with {casing} text but"
        f" the code goes on with {assignment} - other casings of {raw} slip"
        f" past; compare {normalized} instead"
    )


def test_reports_an_emptiness_guard_on_the_raw_name(tmp_path: Path) -> None:
    source = (
        "def require_name(name):\n"
        "    clean_name = name.strip()\n"
        "    if not name:\n"
        "        raise ValueError('name is required')\n"
        "    return clean_name\n"
    )

    assert _report_for(tmp_path, source) == [
        _stripped(3, "name", "clean_name = name.strip()")
    ]


def test_reports_empty_text_and_zero_length_guards(tmp_path: Path) -> None:
    source = (
        "def first_words(text, rows):\n"
        "    trimmed = text.lstrip()\n"
        "    if text == '':\n"
        "        return None\n"
        "    for row in rows:\n"
        "        cell: str = row.rstrip()\n"
        "        if len(row) == 0:\n"
        "            continue\n"
        "        print(cell)\n"
        "    return trimmed.split()[0]\n"
    )

    assert _report_for(tmp_path, source) == [
        _stripped(3, "text", "trimmed = text.lstrip()"),
        _stripped(7, "row", "cell = row.rstrip()"),
    ]


def test_reports_the_line_of_the_guard_part(tmp_path: Path) -> None:
    source = (
        "def login(token, retries):\n"
        "    bare_token = token.strip()\n"
        "    if (\n"
        "        retries > 3\n"
        "        or not token\n"
        "    ):\n"
        "        return None\n"
        "    return bare_token\n"
    )

    assert _report_for(tmp_path, source) == [
        _stripped(5, "token", "bare_token = token.strip()")
    ]


def test_reports_a_stripped_and_folded_copy(tmp_path: Path) -> None:
    source = (
        "def lookup(table, key):\n"
        "    wanted = key.strip().lower()\n"
        "    if not key:\n"
        "        raise KeyError(key)\n"
        "    return table[wanted]\n"
    )

    assert _report_for(tmp_path, source) == [
        _stripped(3, "key", "wanted = key.strip().lower()")
    ]


def test_reports_raw_text_compared_with_lowercase(tmp_path: Path) -> None:
    source = (
        "def parse_flag(answer, role):\n"
        "    folded = answer.lower()\n"
        "    if answer not in ('yes', 'no'):\n"
        "        raise ValueError(answer)\n"
        "    folded_role = role.casefold()\n"
        "    if role == 'admin':\n"
        "        return True\n"
        "    return folded == 'yes' and folded_role != 'guest'\n"
    )

    assert _report_for(tmp_path, source) == [
        _folded(3, "answer", "lowercase", "folded = answer.lower()"),
        _folded(6, "role", "lowercase", "folded_role = role.casefold()"),
    ]


def test_reports_raw_text_compared_with_uppercase(tmp_path: Path) -> None:
    source = (
        "def currency_rate(code, rates):\n"
        "    upper_code = code.upper()\n"
        "    if code in {'USD', 'EUR'}:\n"
        "        return 1.0\n"
        "    return rates[upper_code]\n"
    )

    assert _report_for(tmp_path, source) == [
        _folded(3, "code", "uppercase", "upper_code = code.upper()")
    ]


def test_passes_guards_on_the_normalized_name(tmp_path: Path) -> None:
    source = (
        "def require_name(name, code):\n"
        "    clean_name = name.strip()\n"
        "    if not clean_name:\n"
        "        raise ValueError('name is required')\n"
        "    upper_code = code.upper()\n"
        "    if upper_code in ('USD', 'EUR'):\n"
        "        return clean_name\n"
        "    return clean_name + upper_code\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_copies_that_are_not_plain_normalizations(
    tmp_path: Path,
) -> None:
    source = (
        "def tidy(path, record, name):\n"
        "    bare_path = path.strip('/')\n"
        "    if not path:\n"
        "        return None\n"
        "    record_name = record.name.strip()\n"
        "    if not record:\n"
        "        return None\n"
        "    first = second = name.strip()\n"
        "    if not name:\n"
        "        return None\n"
        "    name = name.strip()\n"
        "    if not name:\n"
        "        return None\n"
        "    return bare_path, record_name, first, second, name\n"
    )

    assert _report_for(tmp_path, source) == []


def test_stops_at_a_new_binding_of_either_name(tmp_path: Path) -> None:
    source = (
        "def require(name, title, default):\n"
        "    clean_name = name.strip()\n"
        "    name = clean_name\n"
        "    if not name:\n"
        "        raise ValueError('name is required')\n"
        "    clean_title = title.strip()\n"
        "    clean_title = clean_title or default\n"
        "    if not title:\n"
        "        raise ValueError('title is required')\n"
        "    return clean_name, clean_title\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_tests_that_do_not_guard(tmp_path: Path) -> None:
    source = (
        "def describe(name, log):\n"
        "    clean_name = name.strip()\n"
        "    if not name:\n"
        "        log('empty name')\n"
        "    if name != '' or name is None:\n"
        "        return clean_name\n"
        "    return clean_name\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_copy_not_used_after_the_guard(tmp_path: Path) -> None:
    source = (
        "def echo(name):\n"
        "    clean_name = name.strip()\n"
        "    print(clean_name)\n"
        "    if not name:\n"
        "        raise ValueError('name is required')\n"
        "    return name\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_test_the_normalization_cannot_change(
    tmp_path: Path,
) -> None:
    source = (
        "def classify(name, label):\n"
        "    folded = name.lower()\n"
        "    if not name:\n"
        "        raise ValueError('name is required')\n"
        "    clean_label = label.strip()\n"
        "    if label == 'admin':\n"
        "        return None\n"
        "    return folded, clean_label\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_texts_of_another_casing(tmp_path: Path) -> None:
    source = (
        "def role_of(name, expected, code):\n"
        "    folded = name.lower()\n"
        "    if name in ('Admin', 'root'):\n"
        "        return None\n"
        "    if name == '42' or name == expected:\n"
        "        return None\n"
        "    if name in ('yes', 1):\n"
        "        return None\n"
        "    upper_code = code.upper()\n"
        "    if code in ('usd', 'eur'):\n"
        "        return None\n"
        "    return folded, upper_code\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_guard_in_a_nested_block(tmp_path: Path) -> None:
    source = (
        "def retry(name, send):\n"
        "    clean_name = name.strip()\n"
        "    for attempt in range(3):\n"
        "        if not name:\n"
        "            break\n"
        "        send(clean_name, attempt)\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    method=st.sampled_from(_STRIPPING_METHODS),
    emptiness_test=st.sampled_from(_EMPTINESS_TESTS),
    tested=st.sampled_from(("raw", "tidy")),
)
def test_guard_property_flags_only_the_raw_name(
    tmp_path: Path, method: str, emptiness_test: str, tested: str
) -> None:
    source = (
        "def clean(raw):\n"
        f"    tidy = raw.{method}()\n"
        f"    if {emptiness_test.format(tested)}:\n"
        "        raise ValueError('empty')\n"
        "    return tidy\n"
    )

    report = _report_for(tmp_path, source)

    expected = [_stripped(3, "raw", f"tidy = raw.{method}()")]
    assert report == (expected if tested == "raw" else [])
