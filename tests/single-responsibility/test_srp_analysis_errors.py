import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from srp_support import CHECK

from python_parsing import parse_python_module
from srp_check import python_file_facts

ANALYSIS_ERROR_EXIT_CODE = 2
DEEP_TERM_COUNT = 700
DEEP_BRANCH_COUNT = 400
SHARED_TEMPORARY_DIRECTORY = [
    HealthCheck.function_scoped_fixture,
    HealthCheck.too_slow,
]
BROKEN_SOURCES = {
    "null_byte": b"value = 1\x00\n",
    "unknown_cookie": b"# -*- coding: klingon -*-\nvalue = 1\n",
    "not_utf8": b"\xe9 = 1\n",
    "bad_syntax": b"def broken(:\n",
}


def long_sum_source(term_count: int) -> str:
    terms = " + ".join("value" for _ in range(term_count))
    return f"def total(value):\n    return {terms}\n"


def long_branch_source(branch_count: int) -> str:
    lines = ["def classify(code):", "    if code == 0:", "        return 0"]
    for branch in range(1, branch_count):
        lines.append(f"    elif code == {branch}:")
        lines.append(f"        return {branch}")
    return "\n".join(lines) + "\n"


def run_check_on(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK / "srp_check.py"), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "source",
    [
        long_sum_source(DEEP_TERM_COUNT),
        long_branch_source(DEEP_BRANCH_COUNT),
    ],
)
def test_deeply_nested_code_is_an_analysis_error(tmp_path, source):
    path = tmp_path / "deep.py"
    path.write_text(source)

    result = run_check_on(path)

    assert result.returncode == ANALYSIS_ERROR_EXIT_CODE
    assert "SRP analysis error" in result.stderr
    assert str(path) in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("name", sorted(BROKEN_SOURCES))
def test_unparsable_source_names_the_file(tmp_path, name):
    path = tmp_path / f"{name}.py"
    path.write_bytes(BROKEN_SOURCES[name])

    result = run_check_on(path)

    assert result.returncode == ANALYSIS_ERROR_EXIT_CODE
    assert str(path) in result.stderr
    assert "None" not in result.stderr


@settings(suppress_health_check=SHARED_TEMPORARY_DIRECTORY, deadline=None)
@given(st.sampled_from(sorted(BROKEN_SOURCES)))
def test_parse_python_module_property_errors_always_name_the_file(
    tmp_path_factory, name
):
    path = tmp_path_factory.mktemp("broken") / f"{name}.py"
    path.write_bytes(BROKEN_SOURCES[name])

    with pytest.raises(SyntaxError) as raised:
        parse_python_module(path)

    assert raised.value.filename == str(path)
    assert raised.value.lineno is not None


@settings(suppress_health_check=SHARED_TEMPORARY_DIRECTORY, deadline=None)
@given(st.integers(min_value=0, max_value=30))
def test_parse_python_module_property_matches_the_source_text(
    tmp_path_factory, term_count
):
    path = tmp_path_factory.mktemp("valid") / "module.py"
    path.write_text(long_sum_source(term_count + 1))

    assert parse_python_module(path).body[0].name == "total"


@settings(suppress_health_check=SHARED_TEMPORARY_DIRECTORY, deadline=None)
@given(st.sampled_from([DEEP_TERM_COUNT, 5]))
def test_python_file_facts_property_deep_code_fails_as_value_error(
    tmp_path_factory, term_count
):
    path = tmp_path_factory.mktemp("depth") / "module.py"
    path.write_text(long_sum_source(term_count))

    if term_count == DEEP_TERM_COUNT:
        with pytest.raises(ValueError, match="module.py"):
            python_file_facts(path)
        return
    assert python_file_facts(path)["path"] == str(path)
