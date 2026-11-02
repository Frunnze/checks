import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "unclosed-resource" / "python" / "unclosed_resources.py"
)


def _report_for(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for relative, source in files.items():
        _ = (tmp_path / relative).write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(files),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _unclosed(path: str, line: int, opened: str) -> str:
    return f"{path}:{line}: {opened} is never closed, returned or handed on"


def test_reports_a_client_whose_request_is_closed(tmp_path: Path) -> None:
    source = (
        "import httpx\n"
        "async def is_up(url):\n"
        "    client: httpx.AsyncClient = httpx.AsyncClient(timeout=5)\n"
        "    async with client.stream('GET', url) as response:\n"
        "        return response.status_code == 200\n"
    )

    assert _report_for(tmp_path, {"probe.py": source}) == [
        _unclosed("probe.py", 3, "client = httpx.AsyncClient(...)")
    ]


def test_reports_imported_and_aliased_factories(tmp_path: Path) -> None:
    source = (
        "from sqlite3 import connect as open_database\n"
        "import zipfile as archives\n"
        "def count(path):\n"
        "    database = open_database(path)\n"
        "    bundle = archives.ZipFile(path)\n"
        "    names = bundle.namelist()\n"
        "    return names, database.execute('SELECT 1').fetchone()\n"
    )

    assert _report_for(tmp_path, {"count.py": source}) == [
        _unclosed("count.py", 4, "database = open_database(...)"),
        _unclosed("count.py", 5, "bundle = archives.ZipFile(...)"),
    ]


def test_skips_project_classes(tmp_path: Path) -> None:
    queue = "class Queue:\n    def close(self):\n        return None\n"
    source = (
        "from queue import Queue\n"
        "def work(items):\n"
        "    pending = Queue()\n"
        "    pending.put(items)\n"
    )

    report = _report_for(tmp_path, {"jobs.py": queue, "work.py": source})

    assert report == []


def test_passes_resources_that_are_released(tmp_path: Path) -> None:
    source = (
        "import httpx, requests, smtplib, subprocess\n"
        "from contextlib import closing\n"
        "def fetch(url, keep):\n"
        "    first = httpx.Client()\n"
        "    with first:\n        first.get(url)\n"
        "    second = requests.Session()\n"
        "    try:\n        second.get(url)\n"
        "    finally:\n        second.close()\n"
        "    third = open(url)\n"
        "    keep(third)\n"
        "    fourth = httpx.Client()\n"
        "    with closing(fourth):\n        fourth.get(url)\n"
        "    fifth = httpx.Client()\n"
        "    process = subprocess.Popen(url)\n"
        "    process.communicate()\n"
        "    mail = smtplib.SMTP(url, timeout=5)\n"
        "    mail.quit()\n"
        "    sixth = httpx.Client()\n"
        "    keep(sixth.close)\n"
        "    return fifth\n"
    )

    assert _report_for(tmp_path, {"fetch.py": source}) == []


@HYPOTHESIS_SETTINGS
@given(
    factory=st.sampled_from(
        [
            "httpx.Client",
            "requests.Session",
            "socket.socket",
            "zipfile.ZipFile",
            "subprocess.Popen",
        ]
    )
)
def test_factory_property_flags_only_the_forgotten_one(
    tmp_path: Path, factory: str
) -> None:
    module = factory.partition(".")[0]
    source = (
        f"import {module}\n"
        "def use(target):\n"
        f"    kept = {factory}(target)\n"
        f"    lost = {factory}(target)\n"
        "    lost.fileno()\n"
        "    kept.close()\n"
    )

    assert _report_for(tmp_path, {"use.py": source}) == [
        _unclosed("use.py", 4, f"lost = {factory}(...)")
    ]
