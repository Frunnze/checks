import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "single-pass-loop" / "python" / "single_pass_loops.py"
)
_ONCE = "this loop never gets past its first item"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "loops.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="loops.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_an_exit_that_slipped_out_of_its_if(tmp_path: Path) -> None:
    source = (
        "def find(users, name):\n"
        "    for user in users:\n"
        "        if user.name == name:\n"
        "            print(user)\n"
        "        return user\n"
        "    return None\n"
    )

    assert _report_for(tmp_path, source) == [
        f"loops.py:2: {_ONCE} - the exit after the if on line 3 runs for"
        " every item"
    ]


def test_reports_a_total_returned_from_the_first_pass(tmp_path: Path) -> None:
    source = (
        "def product(values, prices):\n"
        "    result = 1\n"
        "    for value in values:\n"
        "        result = value * result\n"
        "        return result\n"
        "    total = 0\n"
        "    for price in prices:\n"
        "        total += price\n"
        "        return total\n"
        "    return result + total\n"
    )

    assert _report_for(tmp_path, source) == [
        f"loops.py:3: {_ONCE} - result is built up as if every item were"
        " visited",
        f"loops.py:7: {_ONCE} - total is built up as if every item were"
        " visited",
    ]


def test_reports_a_search_result_returned_unchecked(tmp_path: Path) -> None:
    source = (
        "class Tree:\n"
        "    def find(self, node, key) -> dict | None:\n"
        "        return node.get(key)\n"
        "    def find_in(self, nodes, key) -> dict | None:\n"
        "        for node in nodes:\n"
        "            return self.find(node, key)\n"
        "        return None\n"
    )

    assert _report_for(tmp_path, source) == [
        f"loops.py:5: {_ONCE} - the first item's result is returned even"
        " when it is None"
    ]


def test_passes_deliberate_first_item_idioms(tmp_path: Path) -> None:
    source = (
        "class Box:\n"
        "    def find(self, node, key) -> dict | None:\n"
        "        return node.get(key)\n"
        "    def first(self, items, errors, keys, nodes, found):\n"
        "        for item in items:\n            return item\n"
        "        for item in items:\n            break\n"
        "        for error in errors:\n            raise error\n"
        "        for key in keys:\n"
        "            value = self.pop(key)\n"
        "            return key, value\n"
        "        for node in nodes:\n"
        "            found |= set(node)\n"
        "            break\n"
        "        for node in nodes:\n"
        "            result = self.find(node, 'k')\n"
        "            if result is not None:\n                return result\n"
        "        for item in items:\n"
        "            if not item:\n                continue\n"
        "            return item\n"
        "        raise KeyError\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(operator=st.sampled_from(["+=", "-=", "*=", "|=", "&="]))
def test_total_property_flags_only_a_returned_total(
    tmp_path: Path, operator: str
) -> None:
    source = (
        "def fold(values, total, seen):\n"
        "    for value in values:\n"
        f"        total {operator} value\n"
        "        return total\n"
        "    for value in values:\n"
        f"        seen {operator} value\n"
        "        break\n"
        "    return total, seen\n"
    )

    assert _report_for(tmp_path, source) == [
        f"loops.py:2: {_ONCE} - total is built up as if every item were"
        " visited"
    ]
