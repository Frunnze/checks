import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "cache-across-users" / "python" / "caches_across_users.py"
)
_SERVED = "so one user's answer is served to the next"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "views.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="views.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _served(line: int, function: str, source: str) -> str:
    return (
        f"views.py:{line}: {function}() is cached by its arguments but reads"
        f" {source}, {_SERVED}"
    )


def test_reports_request_data_behind_a_cache(tmp_path: Path) -> None:
    source = (
        "from functools import cache, lru_cache\n"
        "from flask import g, request\n"
        "@lru_cache(maxsize=256)\n"
        "def visible_projects(limit):\n"
        "    return load_projects(owner=g.user.id, limit=limit)\n"
        "@cache\n"
        "def headers():\n"
        "    return dict(request.headers)\n"
    )

    assert _report_for(tmp_path, source) == [
        _served(4, "visible_projects", "g"),
        _served(7, "headers", "request"),
    ]


def test_reports_a_context_variable_behind_a_cache(tmp_path: Path) -> None:
    source = (
        "import functools\n"
        "from contextvars import ContextVar\n"
        "TENANT: ContextVar[str] = ContextVar('tenant')\n"
        "@functools.cache\n"
        "def tenant_settings():\n"
        "    return load_settings(TENANT.get())\n"
    )

    assert _report_for(tmp_path, source) == [
        _served(5, "tenant_settings", "TENANT")
    ]


def test_passes_keyed_and_local_values(tmp_path: Path) -> None:
    source = (
        "from functools import cache\n"
        "from flask import request\n"
        "@cache\n"
        "def locale_for(user_id):\n"
        "    return load_locale(user_id)\n"
        "@cache\n"
        "def colour(text):\n"
        "    r, g, b = parse(text)\n"
        "    return g\n"
        "def page():\n"
        "    return render(request.args)\n"
        "@cache\n"
        "def echo(request):\n"
        "    return request.upper()\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    name=st.sampled_from(["request", "current_user", "g", "session"]),
    decorator=st.sampled_from(["cache", "lru_cache()", "lru_cache"]),
)
def test_cache_property_flags_every_request_name(
    tmp_path: Path, name: str, decorator: str
) -> None:
    source = (
        "from functools import cache, lru_cache\n"
        f"from flask import {name}\n"
        f"@{decorator}\n"
        "def lookup(key):\n"
        f"    return (key, {name})\n"
    )

    assert _report_for(tmp_path, source) == [_served(4, "lookup", name)]
