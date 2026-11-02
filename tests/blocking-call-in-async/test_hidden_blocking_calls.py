import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "blocking-call-in-async" / "python"
    / "hidden_blocking_calls.py"
)
_FIX = " - await it through asyncio.to_thread() or a threadpool"
_BLOCKING_BODIES = {
    "import time": ("time.sleep(1)", "time.sleep()"),
    "import requests": ("requests.get(url, timeout=5)", "requests.get()"),
    "import subprocess": ("subprocess.run(['ls'])", "subprocess.run()"),
    "import sqlite3": ("sqlite3.connect(url)", "sqlite3.connect()"),
    "from urllib.request import urlopen": (
        "urlopen(url, timeout=5)",
        "urllib.request.urlopen()",
    ),
}
_CALL_SHAPES = {
    "direct": "    load(url)\n",
    "assigned": "    page = load(url)\n",
    "threadpool": "    await asyncio.to_thread(load, url)\n",
    "partial": "    await asyncio.to_thread(functools.partial(load, url))\n",
}


def _report_for(tmp_path: Path, modules: dict[str, str]) -> list[str]:
    for name, source in modules.items():
        module = tmp_path / name
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(modules),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _expected(location: str, callee: str, chain: str) -> str:
    return (
        f"{location}: {callee}() blocks the event loop of a request"
        f" handler ({chain}){_FIX}"
    )


def test_reports_a_guard_that_queries_through_a_repository(
    tmp_path: Path,
) -> None:
    modules = {
        "shop/orders.py": (
            "class OrderRepository:\n"
            "    def find_order(self, order_id):\n"
            "        with self._pool.connection() as connection:\n"
            "            return connection.execute(order_id)\n"
            "class OrderService:\n"
            "    def find_order(self, order_id):\n"
            "        return self._repository.find_order(order_id)\n"
        ),
        "shop/guards.py": (
            "def require_order(service, order_id):\n"
            "    order = service.find_order(order_id)\n"
            "    if order is None:\n"
            "        raise LookupError(order_id)\n"
            "    return order\n"
        ),
        "shop/api.py": (
            "from shop.guards import require_order\n"
            "@router.get('/orders/{order_id}')\n"
            "async def show_order(order_id, service):\n"
            "    order = require_order(service, order_id)\n"
            "    return {'order': order}\n"
        ),
    }

    assert _report_for(tmp_path, modules) == [
        _expected(
            "shop/api.py:4",
            "require_order",
            "require_order -> OrderRepository.find_order"
            " -> with .connection()",
        )
    ]


def test_reports_a_method_reached_through_self(tmp_path: Path) -> None:
    source = (
        "import redis\n"
        "class Sessions:\n"
        "    def touch(self, key):\n"
        "        self._remember(key)\n"
        "    def _remember(self, key):\n"
        "        self._redis_client.expire(key, 60)\n"
        "@app.post('/sessions/{key}')\n"
        "async def touch_session(key, sessions):\n"
        "    sessions.touch(key)\n"
    )

    assert _report_for(tmp_path, {"sessions.py": source}) == [
        _expected(
            "sessions.py:9",
            "touch",
            "Sessions.touch -> Sessions._remember -> redis .expire()",
        )
    ]


def test_reports_a_coroutine_awaited_by_a_handler(tmp_path: Path) -> None:
    source = (
        "def read_report(path):\n"
        "    with open(path) as report:\n"
        "        return report.read()\n"
        "class Reports:\n"
        "    async def latest(self, path):\n"
        "        return read_report(path)\n"
        "@app.websocket('/reports')\n"
        "async def stream_reports(socket, reports):\n"
        "    await socket.send(await reports.latest('a.txt'))\n"
    )

    assert _report_for(tmp_path, {"reports.py": source}) == [
        _expected("reports.py:6", "read_report", "read_report -> open()")
    ]


def test_reports_client_and_socket_calls(tmp_path: Path) -> None:
    source = (
        "import httpx\n"
        "import socket\n"
        "def resolve(host):\n"
        "    return socket.getaddrinfo(host, 443)\n"
        "def ping(url):\n"
        "    with httpx.Client(timeout=5) as client:\n"
        "        return client.get(url)\n"
        "@app.exception_handler(ValueError)\n"
        "async def explain(request, error):\n"
        "    resolve(request.host)\n"
        "    return ping(request.url)\n"
    )

    assert _report_for(tmp_path, {"probe.py": source}) == [
        _expected("probe.py:10", "resolve", "resolve -> socket.getaddrinfo()"),
        _expected("probe.py:11", "ping", "ping -> with httpx.Client()"),
    ]


def test_passes_offloaded_and_awaited_calls(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "import functools\n"
        "import time\n"
        "from starlette.concurrency import run_in_threadpool\n"
        "def slow(seconds):\n"
        "    time.sleep(seconds)\n"
        "async def pause(seconds):\n"
        "    await asyncio.sleep(seconds)\n"
        "@app.get('/wait')\n"
        "async def wait(seconds):\n"
        "    await run_in_threadpool(slow, seconds)\n"
        "    await asyncio.to_thread(functools.partial(slow, seconds))\n"
        "    loop = asyncio.get_running_loop()\n"
        "    await loop.run_in_executor(None, lambda: slow(seconds))\n"
        "    await pause(seconds)\n"
    )

    assert _report_for(tmp_path, {"waiting.py": source}) == []


def test_passes_code_outside_a_request_handler(tmp_path: Path) -> None:
    source = (
        "import time\n"
        "def slow():\n"
        "    time.sleep(1)\n"
        "async def run_job():\n"
        "    slow()\n"
        "@app.get('/sync')\n"
        "def sync_endpoint():\n"
        "    slow()\n"
        "@functools.cache\n"
        "async def cached():\n"
        "    slow()\n"
    )

    assert _report_for(tmp_path, {"jobs.py": source}) == []


def test_passes_a_helper_that_blocks_only_on_some_paths(
    tmp_path: Path,
) -> None:
    source = (
        "import time\n"
        "def cached_value(cache, key):\n"
        "    if key in cache:\n"
        "        return cache[key]\n"
        "    time.sleep(1)\n"
        "    return None\n"
        "def maybe_wait(flag):\n"
        "    if flag:\n"
        "        time.sleep(1)\n"
        "    return flag and time.sleep(1)\n"
        "@app.get('/value')\n"
        "async def value(cache, key):\n"
        "    maybe_wait(key)\n"
        "    return cached_value(cache, key)\n"
    )

    assert _report_for(tmp_path, {"cache.py": source}) == []


def test_passes_names_it_cannot_tie_to_one_blocking_definition(
    tmp_path: Path,
) -> None:
    source = (
        "import time\n"
        "class SlowStore:\n"
        "    def get(self, key):\n"
        "        time.sleep(1)\n"
        "    def load(self, key):\n"
        "        time.sleep(1)\n"
        "class MemoryStore:\n"
        "    def load(self, key):\n"
        "        return key\n"
        "class StoreProtocol:\n"
        "    def save(self, key):\n"
        "        ...\n"
        "@app.get('/stores/{key}')\n"
        "async def read(key, store, settings):\n"
        "    settings.get(key)\n"
        "    store.load(key)\n"
        "    store.save(key)\n"
    )

    assert _report_for(tmp_path, {"stores.py": source}) == []


@HYPOTHESIS_SETTINGS
@given(
    blocking=st.sampled_from(sorted(_BLOCKING_BODIES)),
    shape=st.sampled_from(sorted(_CALL_SHAPES)),
)
def test_blocking_property_flags_only_a_direct_call(
    tmp_path: Path, blocking: str, shape: str
) -> None:
    body, label = _BLOCKING_BODIES[blocking]
    source = (
        "import asyncio\n"
        "import functools\n"
        f"{blocking}\n"
        "def load(url):\n"
        f"    return {body}\n"
        "@app.post('/load')\n"
        "async def handle(url):\n"
        f"{_CALL_SHAPES[shape]}"
    )

    report = _report_for(tmp_path, {"loader.py": source})

    if shape in {"direct", "assigned"}:
        assert report == [
            _expected("loader.py:8", "load", f"load -> {label}")
        ]
    else:
        assert report == []
