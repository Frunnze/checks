import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "lazy-init-race" / "python"
    / "lazy_initialization_races.py"
)
_LOCKS = [
    "self._lock",
    "self._get_lock()",
    "self._engine_mutex",
    "self._locks[name]",
    "self._start_semaphore",
]
_UNSET_TESTS = ["self._engine is None", "not self._engine"]


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "engines.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="engines.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _message(line_number: int, value: str, lock: str) -> str:
    return (
        f"engines.py:{line_number}: {value} is tested before taking {lock}"
        " but set under it without a second test, so two callers can both"
        f" set it - test {value} again inside the lock before setting it"
    )


def test_reports_an_early_return_without_a_second_test(
    tmp_path: Path,
) -> None:
    source = (
        "class Engines:\n"
        "    @classmethod\n"
        "    async def get(cls):\n"
        "        if cls._engine is not None:\n"
        "            return cls._engine\n"
        "        async with cls._get_lock():\n"
        "            engine = await open_engine()\n"
        "            cls._engine = engine\n"
        "        return cls._engine\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(6, "cls._engine", "cls._get_lock()")
    ]


def test_reports_an_enclosing_test_without_a_second_test(
    tmp_path: Path,
) -> None:
    source = (
        "import threading\n"
        "_ENGINE_LOCK = threading.Lock()\n"
        "_engine = None\n"
        "def engine():\n"
        "    global _engine\n"
        "    if _engine is None and ENABLED:\n"
        "        log('opening')\n"
        "        with _ENGINE_LOCK:\n"
        "            _engine = open_engine()\n"
        "    return _engine\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(8, "_engine", "_ENGINE_LOCK")
    ]


def test_reports_a_keyed_cache_filled_without_a_second_test(
    tmp_path: Path,
) -> None:
    source = (
        "class Sessions:\n"
        "    def session(self, name):\n"
        "        if name in self._sessions:\n"
        "            return self._sessions[name]\n"
        "        with self._sessions_lock:\n"
        "            self._sessions[name] = open_session(name)\n"
        "        return self._sessions[name]\n"
        "    def pool(self, name):\n"
        "        if name not in POOLS:\n"
        "            with threading.RLock():\n"
        "                POOLS[name] = make_pool(name)\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(5, "self._sessions", "self._sessions_lock"),
        _message(10, "POOLS", "threading.RLock()"),
    ]


def test_passes_double_checked_locking(tmp_path: Path) -> None:
    source = (
        "class Engines:\n"
        "    def first(self):\n"
        "        if self._engine is None:\n"
        "            with self._lock:\n"
        "                if self._engine is None:\n"
        "                    self._engine = open_engine()\n"
        "        return self._engine\n"
        "    def second(self):\n"
        "        if self._engine is not None:\n"
        "            return self._engine\n"
        "        with self._lock:\n"
        "            existing = self._engine\n"
        "            if existing is not None:\n"
        "                return existing\n"
        "            self._engine = open_engine()\n"
        "        return self._engine\n"
        "    def third(self):\n"
        "        if not self._engine:\n"
        "            with self._lock:\n"
        "                self._engine = self._engine or open_engine()\n"
        "        return self._engine\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_shapes_that_are_not_a_lazy_initialization(
    tmp_path: Path,
) -> None:
    source = (
        "class Engines:\n"
        "    def locked_only(self):\n"
        "        with self._lock:\n"
        "            self._engine = open_engine()\n"
        "    def flag(self):\n"
        "        if self._closed:\n"
        "            return\n"
        "        with self._lock:\n"
        "            self._closed = True\n"
        "    def outside(self):\n"
        "        if self._engine is None:\n"
        "            with self._lock:\n"
        "                engine = open_engine()\n"
        "            self._engine = engine\n"
        "    def not_a_lock(self, path):\n"
        "        if self._engine is None:\n"
        "            with self.clock, open(path) as block:\n"
        "                self._engine = parse(block)\n"
        "    def local(self):\n"
        "        engine = None\n"
        "        if engine is None:\n"
        "            with self._lock:\n"
        "                engine = open_engine()\n"
        "        return engine\n"
        "    def other_value(self):\n"
        "        if self._engine is None:\n"
        "            with self._lock:\n"
        "                self._pool = open_pool()\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    lock=st.sampled_from(_LOCKS),
    unset_test=st.sampled_from(_UNSET_TESTS),
    is_tested_again=st.booleans(),
)
def test_lock_property_flags_only_the_missing_second_test(
    tmp_path: Path, lock: str, unset_test: str, *, is_tested_again: bool
) -> None:
    assignment = "self._engine = open_engine(name)"
    lock_body = (
        f"                if {unset_test}:\n"
        f"                    {assignment}\n"
        if is_tested_again
        else f"                {assignment}\n"
    )
    source = (
        "class Engines:\n"
        "    def engine(self, name):\n"
        f"        if {unset_test}:\n"
        f"            with {lock}:\n"
        f"{lock_body}"
        "        return self._engine\n"
    )

    expected = (
        [] if is_tested_again else [_message(4, "self._engine", lock)]
    )

    assert _report_for(tmp_path, source) == expected
