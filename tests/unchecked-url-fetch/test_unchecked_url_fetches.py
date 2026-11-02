import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "unchecked-url-fetch" / "python" / "unchecked_url_fetches.py"
)
_REACH = "as a URL unchecked, so callers reach internal hosts"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "preview.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="preview.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _fetch(line: int, handler: str, parameter: str) -> str:
    return (
        f"preview.py:{line}: {handler}() fetches the request value"
        f" {parameter} {_REACH}"
    )


def test_reports_module_and_client_fetches(tmp_path: Path) -> None:
    source = (
        "import httpx\n"
        "import requests\n"
        "@app.get('/preview')\n"
        "def preview(url):\n"
        "    return requests.get(url, timeout=5).text\n"
        "@app.post('/hook')\n"
        "async def hook(target):\n"
        "    async with httpx.AsyncClient() as client:\n"
        "        return await client.post(target)\n"
    )

    assert _report_for(tmp_path, source) == [
        _fetch(5, "preview", "url"),
        _fetch(9, "hook", "target"),
    ]


def test_passes_checked_urls_and_plain_functions(tmp_path: Path) -> None:
    source = (
        "import requests\n"
        "@app.get('/safe')\n"
        "def safe(url):\n"
        "    ensure_public_url(url)\n"
        "    return requests.get(url, timeout=5).text\n"
        "@app.get('/fixed')\n"
        "def fixed(query):\n"
        "    return requests.get('https://api.example.com', params=query)\n"
        "def download(url):\n"
        "    return requests.get(url, timeout=5).content\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    client=st.sampled_from(["requests", "httpx"]),
    method=st.sampled_from(["get", "post", "put", "delete", "head"]),
)
def test_fetch_property_flags_every_client_method(
    tmp_path: Path, client: str, method: str
) -> None:
    source = (
        f"import {client}\n"
        "@router.post('/fetch')\n"
        "def fetch(address):\n"
        f"    return {client}.{method}(address, timeout=5)\n"
    )

    assert _report_for(tmp_path, source) == [_fetch(4, "fetch", "address")]
