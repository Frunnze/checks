import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "unlocked-check" / "python"
    / "unlocked_checks.py"
)
_GUARDS_ELSEWHERE = "the lock that guards it elsewhere"
_TAKEN_HERE = "the lock this method takes"
_LOCKS = [
    "self._lock",
    "self._mutex",
    "self._state_lock.write()",
    "self.cache_lock",
]
_CHECKS_AND_SETS = [
    ("key not in self._cache", "self._cache[key] = build(key)"),
    ("self._cache is None", "self._cache = build(key)"),
    ("not self._cache", "self._cache: dict = build(key)"),
]


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "stores.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="stores.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _message(line_number: int, attribute: str, lock: str) -> str:
    return (
        f"stores.py:{line_number}: self.{attribute} is checked then set"
        f" outside {lock}, so two threads can both pass the check - do the"
        " check and the set under the lock"
    )


def test_reports_a_cache_filled_outside_the_lock_that_guards_it(
    tmp_path: Path,
) -> None:
    source = (
        "class Registry:\n"
        "    def clear(self):\n"
        "        with self._lock:\n"
        "            self.entries.clear()\n"
        "    def entry(self, key):\n"
        "        if key not in self.entries:\n"
        "            self.entries[key] = build(key)\n"
        "        return self.entries[key]\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(6, "entries", _GUARDS_ELSEWHERE)
    ]


def test_reports_a_check_next_to_the_lock_this_method_takes(
    tmp_path: Path,
) -> None:
    source = (
        "class Pool:\n"
        "    def connection(self, name):\n"
        "        with self._mutex:\n"
        "            self.requests += 1\n"
        "        if self.client is None:\n"
        "            self.client: Client = connect(name)\n"
        "        return self.client\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(5, "client", _TAKEN_HERE)
    ]


def test_reports_a_flag_guarded_through_a_lock_method(
    tmp_path: Path,
) -> None:
    source = (
        "class Worker:\n"
        "    def stop(self):\n"
        "        with self._state_lock.write():\n"
        "            self.started = False\n"
        "    def start(self):\n"
        "        if not self.started:\n"
        "            self.started = True\n"
        "            launch()\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(6, "started", _GUARDS_ELSEWHERE)
    ]


def test_reports_a_check_after_the_manual_release(tmp_path: Path) -> None:
    source = (
        "class Registry:\n"
        "    def entry(self, key):\n"
        "        self._lock.acquire()\n"
        "        self.reads += 1\n"
        "        self._lock.release()\n"
        "        if key not in self.reads_by_key:\n"
        "            self.reads_by_key[key] = 0\n"
        "    def reset(self):\n"
        "        with self._lock:\n"
        "            self.reads_by_key = {}\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(6, "reads_by_key", _GUARDS_ELSEWHERE)
    ]


def test_passes_checks_inside_the_lock(tmp_path: Path) -> None:
    source = (
        "class Registry:\n"
        "    def entry(self, key):\n"
        "        with self._lock:\n"
        "            if key not in self.entries:\n"
        "                self.entries[key] = build(key)\n"
        "            return self.entries[key]\n"
        "    def client(self):\n"
        "        if self._client is None:\n"
        "            with self._lock:\n"
        "                if self._client is None:\n"
        "                    self._client = connect()\n"
        "        return self._client\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_manually_locked_regions(tmp_path: Path) -> None:
    source = (
        "class Registry:\n"
        "    def entry(self, key):\n"
        "        self._lock.acquire()\n"
        "        if key not in self.entries:\n"
        "            self.entries[key] = build(key)\n"
        "        self._lock.release()\n"
        "    def client(self):\n"
        "        try:\n"
        "            if self._client is None:\n"
        "                self._client = connect()\n"
        "        finally:\n"
        "            self._lock.release()\n"
        "    def reset(self):\n"
        "        with self._lock:\n"
        "            self.entries = {}\n"
        "            self._client = None\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_the_initializer_and_async_methods(tmp_path: Path) -> None:
    source = (
        "class Registry:\n"
        "    def __init__(self):\n"
        "        if self.entries is None:\n"
        "            self.entries = {}\n"
        "    async def entry(self, key):\n"
        "        if key not in self.entries:\n"
        "            self.entries[key] = await build(key)\n"
        "    def reset(self):\n"
        "        with self._lock:\n"
        "            self.entries = {}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_class_with_only_async_locks(tmp_path: Path) -> None:
    source = (
        "class Registry:\n"
        "    def entry(self, key):\n"
        "        if key not in self.entries:\n"
        "            self.entries[key] = build(key)\n"
        "    async def reset(self):\n"
        "        async with self._lock:\n"
        "            self.entries = {}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_lock_created_on_first_use(tmp_path: Path) -> None:
    source = (
        "import threading\n"
        "class Registry:\n"
        "    def entry(self, key):\n"
        "        if self._entries_lock is None:\n"
        "            self._entries_lock = threading.Lock()\n"
        "        with self._entries_lock:\n"
        "            return self.entries.get(key)\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_attributes_the_lock_never_touches(tmp_path: Path) -> None:
    source = (
        "class Registry:\n"
        "    def entry(self, key):\n"
        "        if self.label is None:\n"
        "            self.label = 'registry'\n"
        "        if key not in self.entries:\n"
        "            log(key)\n"
        "        else:\n"
        "            self.entries[key] = build(key)\n"
        "        if self.cache is None:\n"
        "            self.other = build(key)\n"
        "    def reset(self):\n"
        "        with self._lock:\n"
        "            self.entries = {}\n"
        "            self.cache = None\n"
        "class Plain:\n"
        "    def entry(self, key):\n"
        "        if key not in self.entries:\n"
        "            self.entries[key] = build(key)\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    lock=st.sampled_from(_LOCKS),
    check_and_set=st.sampled_from(_CHECKS_AND_SETS),
    is_locked=st.booleans(),
)
def test_lock_property_flags_only_the_unlocked_check(
    tmp_path: Path,
    lock: str,
    check_and_set: tuple[str, str],
    *,
    is_locked: bool,
) -> None:
    check, assignment = check_and_set
    body = (
        f"        with {lock}:\n"
        f"            if {check}:\n"
        f"                {assignment}\n"
        if is_locked
        else f"        if {check}:\n            {assignment}\n"
    )
    source = (
        "class Store:\n"
        "    def clear(self):\n"
        f"        with {lock}:\n"
        "            self._cache.clear()\n"
        "    def get(self, key):\n"
        f"{body}"
        "        return self._cache[key]\n"
    )
    expected = (
        [] if is_locked else [_message(6, "_cache", _GUARDS_ELSEWHERE)]
    )

    assert _report_for(tmp_path, source) == expected
