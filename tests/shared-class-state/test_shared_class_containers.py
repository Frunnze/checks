import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "shared-class-state" / "python"
    / "shared_class_containers.py"
)
_CONTAINERS = {
    "set()": ("set", "self.seen.add(item)"),
    "[]": ("list", "self.seen.append(item)"),
    "{}": ("dict", "self.seen.update({item: True})"),
    "dict()": ("dict", "self.seen.pop(item, None)"),
    "deque()": ("deque", "self.seen.appendleft(item)"),
    "defaultdict(int)": ("defaultdict", "self.seen.clear()"),
    "collections.OrderedDict()": ("OrderedDict", "self.seen.popitem()"),
}


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "basket.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="basket.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _message(
    line_number: int, owner: str, name: str, kind: str, mutation_line: int
) -> str:
    return (
        f"basket.py:{line_number}: {owner}.{name} is one {kind} shared by"
        f" every instance, yet line {mutation_line} changes it through self"
        f" - create it per instance in __init__ (self.{name} = ...), or"
        " reach it through the class if sharing is intended"
    )


def test_reports_a_class_variable_set_filled_through_self(
    tmp_path: Path,
) -> None:
    source = (
        "from typing import ClassVar\n"
        "class Basket:\n"
        "    _picked_ids: ClassVar[set[str]] = set()\n"
        "    def __init__(self, store):\n"
        "        self.store = store\n"
        "    def pick(self, item_id):\n"
        "        if item_id in self._picked_ids:\n"
        "            return False\n"
        "        self._picked_ids.add(item_id)\n"
        "        return True\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(3, "Basket", "_picked_ids", "set", 9)
    ]


def test_reports_lists_and_dicts_changed_in_place(tmp_path: Path) -> None:
    source = (
        "class Basket:\n"
        "    items = []\n"
        "    totals: dict[str, int] = {}\n"
        "    history = list()\n"
        "    async def add(self, name, price):\n"
        "        self.items += [name]\n"
        "        self.totals[name] = price\n"
        "    def forget(self, name):\n"
        "        del self.totals[name]\n"
        "        self.history.extend([name])\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(2, "Basket", "items", "list", 6),
        _message(4, "Basket", "history", "list", 10),
    ]


def test_passes_a_cache_filled_by_key(tmp_path: Path) -> None:
    source = (
        "class Compiler:\n"
        "    _compiled = {}\n"
        "    def compile(self, pattern):\n"
        "        if pattern not in self._compiled:\n"
        "            self._compiled[pattern] = pattern.upper()\n"
        "        return self._compiled[pattern]\n"
    )

    assert _report_for(tmp_path, source) == []


def test_a_class_variable_is_shared_even_in_a_model(tmp_path: Path) -> None:
    source = (
        "from typing import ClassVar\n"
        "class Basket(BaseModel):\n"
        "    tags: list[str] = []\n"
        "    _seen: ClassVar[list[str]] = []\n"
        "    def tag(self, label):\n"
        "        self.tags.append(label)\n"
        "        self._seen.append(label)\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(4, "Basket", "_seen", "list", 7)
    ]


def test_passes_containers_each_instance_owns(tmp_path: Path) -> None:
    source = (
        "class Basket:\n"
        "    items = []\n"
        "    def __init__(self):\n"
        "        self.items = []\n"
        "    def add(self, name):\n"
        "        self.items.append(name)\n"
        "class Reset:\n"
        "    names = set()\n"
        "    def clear(self):\n"
        "        self.names = set()\n"
        "    def add(self, name):\n"
        "        self.names.add(name)\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_state_that_is_shared_on_purpose(tmp_path: Path) -> None:
    source = (
        "import dataclasses\n"
        "class Plugins:\n"
        "    _known = {}\n"
        "    _active = []\n"
        "    _order_cache = {}\n"
        "    @classmethod\n"
        "    def register(cls, name, plugin):\n"
        "        cls._known[name] = plugin\n"
        "    def activate(self, name):\n"
        "        self._known.pop(name)\n"
        "        Plugins._active.append(name)\n"
        "        type(self)._active.append(name)\n"
        "        self._active.append(name)\n"
        "        self._order_cache[name] = len(self._active)\n"
        "    @staticmethod\n"
        "    def reset(other):\n"
        "        other._order_cache.clear()\n"
        "@dataclasses.dataclass\n"
        "class Settings:\n"
        "    flags: dict = {}\n"
        "    def enable(self, name):\n"
        "        self.flags[name] = True\n"
        "class Order(BaseModel):\n"
        "    lines: list[str] = []\n"
        "    def add(self, line):\n"
        "        self.lines.append(line)\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_what_is_never_changed_or_not_shared(tmp_path: Path) -> None:
    source = (
        "class Basket:\n"
        "    ALLOWED = {'apple', 'pear'}\n"
        "    SIZES = ('s', 'm')\n"
        "    frozen = frozenset()\n"
        "    def allowed(self, name):\n"
        "        return name in self.ALLOWED\n"
        "    def merge(self, other):\n"
        "        other.ALLOWED.add('plum')\n"
        "        return self.ALLOWED | {'plum'}\n"
        "def collect():\n"
        "    class Collector:\n"
        "        parts = []\n"
        "        def write(self, part):\n"
        "            self.parts.append(part)\n"
        "    return Collector()\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    container=st.sampled_from(sorted(_CONTAINERS)),
    is_rebound=st.booleans(),
)
def test_container_property_flags_only_the_shared_one(
    tmp_path: Path, container: str, *, is_rebound: bool
) -> None:
    kind, mutation = _CONTAINERS[container]
    rebinding = f"        self.seen = {container}\n" if is_rebound else ""
    source = (
        "import collections\n"
        "from collections import defaultdict, deque\n"
        "class Tracker:\n"
        f"    seen = {container}\n"
        "    def __init__(self):\n"
        "        self.count = 0\n"
        f"{rebinding}"
        "    def track(self, item):\n"
        f"        {mutation}\n"
    )

    expected = (
        [] if is_rebound else [_message(4, "Tracker", "seen", kind, 8)]
    )

    assert _report_for(tmp_path, source) == expected
