import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "missing-timeout" / "python"
    / "missing_timeouts.py"
)
_CLIENTS = {
    "redis.Redis(host='cache'{})": ("redis.Redis", "socket_timeout"),
    "redis.from_url(url{})": ("redis.from_url", "socket_timeout"),
    "redis.asyncio.Redis.from_url(url{})": (
        "redis.asyncio.Redis.from_url",
        "socket_timeout",
    ),
    "smtplib.SMTP('mail'{})": ("smtplib.SMTP", "timeout"),
    "ftplib.FTP('files'{})": ("ftplib.FTP", "timeout"),
    "imaplib.IMAP4_SSL('inbox'{})": ("imaplib.IMAP4_SSL", "timeout"),
    "socket.create_connection(address{})": (
        "socket.create_connection",
        "timeout",
    ),
    "http.client.HTTPConnection('api'{})": (
        "http.client.HTTPConnection",
        "timeout",
    ),
}
_IMPORTS = (
    "import ftplib\n"
    "import http.client\n"
    "import imaplib\n"
    "import redis\n"
    "import redis.asyncio\n"
    "import smtplib\n"
    "import socket\n"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "clients.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="clients.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _expected(line: int, client: str, option: str) -> str:
    return (
        f"clients.py:{line}: {client}() has no {option}, so a stalled peer"
        f" blocks it forever - pass {option}="
    )


def test_reports_a_redis_client_with_only_a_connect_timeout(
    tmp_path: Path,
) -> None:
    source = (
        "import redis\n"
        "def build_cache(url):\n"
        "    return redis.from_url(\n"
        "        url,\n"
        "        socket_connect_timeout=2,\n"
        "    )\n"
    )

    assert _report_for(tmp_path, source) == [
        _expected(3, "redis.from_url", "socket_timeout")
    ]


def test_resolves_imported_names_and_aliases(tmp_path: Path) -> None:
    source = (
        "import redis.asyncio as aioredis\n"
        "from redis import Redis\n"
        "from redis.asyncio import ConnectionPool\n"
        "from urllib.request import urlopen\n"
        "from http import client as http_client\n"
        "def connect(url):\n"
        "    sync_cache = Redis(host='cache', port=6379)\n"
        "    async_cache = aioredis.from_url(url)\n"
        "    pool = ConnectionPool.from_url(url, max_connections=4)\n"
        "    page = urlopen(url)\n"
        "    api = http_client.HTTPSConnection('api.example.com')\n"
        "    return sync_cache, async_cache, pool, page, api\n"
    )

    assert _report_for(tmp_path, source) == [
        _expected(7, "redis.Redis", "socket_timeout"),
        _expected(8, "redis.asyncio.from_url", "socket_timeout"),
        _expected(
            9, "redis.asyncio.ConnectionPool.from_url", "socket_timeout"
        ),
        _expected(10, "urllib.request.urlopen", "timeout"),
        _expected(11, "http.client.HTTPSConnection", "timeout"),
    ]


def test_reports_a_postgres_connection_without_connect_timeout(
    tmp_path: Path,
) -> None:
    source = (
        "import psycopg2\n"
        "def open_database():\n"
        "    first = psycopg2.connect(host='db', dbname='shop')\n"
        "    second = psycopg2.connect('host=db dbname=shop')\n"
        "    return first, second\n"
    )

    assert _report_for(tmp_path, source) == [
        _expected(3, "psycopg2.connect", "connect_timeout"),
        _expected(4, "psycopg2.connect", "connect_timeout"),
    ]


def test_passes_timeouts_given_by_keyword_or_position(
    tmp_path: Path,
) -> None:
    source = (
        "import smtplib\n"
        "import socket\n"
        "import redis\n"
        "from urllib.request import urlopen\n"
        "def connect(url, address):\n"
        "    urlopen(url, None, 5)\n"
        "    urlopen(url, timeout=5)\n"
        "    socket.create_connection(address, 5)\n"
        "    smtplib.SMTP('mail', 25, None, 10)\n"
        "    redis.Redis('cache', 6379, 0, None, 5)\n"
        "    redis.from_url(url, socket_timeout=5)\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_settings_the_call_cannot_see(tmp_path: Path) -> None:
    source = (
        "import psycopg2\n"
        "import redis\n"
        "import smtplib\n"
        "def connect(dsn, options, arguments, pool):\n"
        "    redis.Redis(**options)\n"
        "    smtplib.SMTP(*arguments)\n"
        "    redis.Redis(connection_pool=pool)\n"
        "    redis.from_url('redis://cache:6379/0?socket_timeout=5')\n"
        "    psycopg2.connect(dsn)\n"
        "    psycopg2.connect(dsn=dsn)\n"
        "    psycopg2.connect('host=db connect_timeout=5')\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_clients_outside_the_catalogue(tmp_path: Path) -> None:
    source = (
        "import httpx\n"
        "import psycopg\n"
        "class Redis:\n"
        "    def __init__(self, host):\n"
        "        self.host = host\n"
        "def connect(url):\n"
        "    cache = Redis(host='cache')\n"
        "    database = psycopg.connect(url)\n"
        "    client = httpx.Client()\n"
        "    return cache, database, client\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    client=st.sampled_from(sorted(_CLIENTS)),
    has_timeout=st.booleans(),
)
def test_timeout_property_flags_only_a_missing_option(
    tmp_path: Path, client: str, has_timeout: bool
) -> None:
    name, option = _CLIENTS[client]
    timeout = f", {option}=5" if has_timeout else ""
    source = (
        f"{_IMPORTS}"
        "def connect(url, address):\n"
        f"    return {client.format(timeout)}\n"
    )

    report = _report_for(tmp_path, source)

    if has_timeout:
        assert report == []
    else:
        assert report == [_expected(9, name, option)]
