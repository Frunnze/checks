import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "permissive-default" / "python" / "permissive_defaults.py"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "settings.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="settings.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_each_kind_of_unsafe_default(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "from os import getenv\n"
        "DEBUG = os.getenv('APP_DEBUG', 'True')\n"
        "VERIFY = os.environ.get('SSL_VERIFY', '0')\n"
        "ORIGINS = getenv('CORS_ALLOWED_ORIGINS', '*')\n"
        "SECRET_KEY = os.environ.get('JWT_SECRET', 'dev-secret')\n"
    )

    assert _report_for(tmp_path, source) == [
        "settings.py:3: APP_DEBUG falls back to 'True' when unset - it"
        " switches the unsafe mode on",
        "settings.py:4: SSL_VERIFY falls back to '0' when unset - it switches"
        " the protection off",
        "settings.py:5: CORS_ALLOWED_ORIGINS falls back to '*' when unset -"
        " it allows every origin",
        "settings.py:6: JWT_SECRET falls back to 'dev-secret' when unset -"
        " every deployment shares this secret",
    ]


def test_passes_safe_and_harmless_defaults(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "DEBUG = os.getenv('APP_DEBUG', 'false')\n"
        "VERIFY = os.environ.get('SSL_VERIFY', 'true')\n"
        "SECRET = os.environ['JWT_SECRET']\n"
        "TOKEN_URL = os.getenv('AUTH_TOKEN_URL', 'https://example.com')\n"
        "KEY_PATH = os.getenv('API_KEY_PATH', '/run/secrets/key')\n"
        "EMPTY = os.getenv('API_KEY', '')\n"
        "HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost')\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    setting=st.sampled_from(
        ["VERIFY_TLS", "REQUIRE_AUTH", "CSRF_ENABLED", "SESSION_SECURE"]
    ),
    off=st.sampled_from(["0", "false", "False", "no", "off"]),
)
def test_switch_property_flags_every_off_spelling(
    tmp_path: Path, setting: str, off: str
) -> None:
    source = (
        "import os\n"
        f"OFF = os.getenv('{setting}', '{off}')\n"
        f"ON = os.getenv('{setting}', 'true')\n"
    )

    assert _report_for(tmp_path, source) == [
        f"settings.py:2: {setting} falls back to '{off}' when unset - it"
        " switches the protection off"
    ]
