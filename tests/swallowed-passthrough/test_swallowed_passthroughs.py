import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_DEEP_TERMS = 1000
_FINDER = (
    _CHECKS / "experimental" / "swallowed-passthrough" / "python"
    / "swallowed_passthroughs.py"
)
_FETCH = (
    "class Fetcher:\n"
    "    def fetch(self, key):\n"
    "        try:\n"
    "            return self._client.get(key)\n"
    "        except QuotaExceeded:\n"
    "            raise\n"
    "        except Exception:\n"
    "            return None\n"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "fetching.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="fetching.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _sibling(handlers: str) -> str:
    return (
        "    def fetch_many(self, keys):\n"
        "        try:\n"
        "            return self._client.get_many(keys)\n"
        f"{handlers}"
    )


def test_reports_a_sibling_method_that_drops_the_passthrough(
    tmp_path: Path,
) -> None:
    source = _FETCH + _sibling(
        "        except Exception as error:\n"
        "            log_failure(keys, error)\n"
        "            return []\n"
    )

    assert _report_for(tmp_path, source) == [
        "fetching.py:12: except Exception swallows QuotaExceeded, which"
        " fetch() in this class lets through - add \"except"
        " QuotaExceeded: raise\" above it"
    ]


def test_reports_module_functions_around_one_client(tmp_path: Path) -> None:
    source = (
        "def load(name):\n"
        "    try:\n"
        "        return client.read(name)\n"
        "    except (KeyboardInterrupt, auth.Expired):\n"
        "        cleanup()\n"
        "        raise\n"
        "    except Exception:\n"
        "        return None\n"
        "def load_all():\n"
        "    try:\n"
        "        return client.read_all()\n"
        "    except BaseException:\n"
        "        return []\n"
        "def load_some():\n"
        "    try:\n"
        "        return client.read_some()\n"
        "    except Exception:\n"
        "        return []\n"
    )

    assert _report_for(tmp_path, source) == [
        "fetching.py:12: except BaseException swallows KeyboardInterrupt,"
        " auth.Expired, which load() in this module lets through - add"
        " \"except (KeyboardInterrupt, auth.Expired): raise\" above it",
        "fetching.py:17: except Exception swallows auth.Expired, which"
        " load() in this module lets through - add \"except"
        " auth.Expired: raise\" above it",
    ]


def test_reports_a_bare_except(tmp_path: Path) -> None:
    source = _FETCH + _sibling(
        "        except:\n"
        "            pass\n"
    )

    assert _report_for(tmp_path, source) == [
        "fetching.py:12: a bare except swallows QuotaExceeded, which"
        " fetch() in this class lets through - add \"except"
        " QuotaExceeded: raise\" above it"
    ]


def test_passes_handlers_that_raise_keep_or_name_the_error(
    tmp_path: Path,
) -> None:
    source = (
        _FETCH
        + _sibling(
            "        except Exception as error:\n"
            "            raise FetchFailed(keys) from error\n"
        )
        + "    def fetch_later(self, key):\n"
        "        try:\n"
        "            self._client.get(key)\n"
        "        except Exception as error:\n"
        "            self.failure = error\n"
        "    def fetch_or_none(self, key):\n"
        "        try:\n"
        "            return self._client.get(key)\n"
        "        except QuotaExceeded:\n"
        "            return None\n"
        "        except Exception:\n"
        "            return None\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_tries_that_are_not_siblings(tmp_path: Path) -> None:
    source = (
        "class Fetcher:\n"
        "    def fetch(self, key):\n"
        "        try:\n"
        "            return self._client.get(key)\n"
        "        except QuotaExceeded:\n"
        "            raise\n"
        "        except Exception:\n"
        "            pass\n"
        "        try:\n"
        "            return self._client.get(key)\n"
        "        except Exception:\n"
        "            return None\n"
        "    def close(self):\n"
        "        try:\n"
        "            self._socket.close()\n"
        "        except Exception:\n"
        "            pass\n"
        "    def poll(self):\n"
        "        try:\n"
        "            while True:\n"
        "                self._client.get('status')\n"
        "        except Exception:\n"
        "            pass\n"
        "class Other:\n"
        "    def fetch(self, key):\n"
        "        try:\n"
        "            return self._client.get(key)\n"
        "        except Exception:\n"
        "            return None\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_try_with_its_own_passthrough(tmp_path: Path) -> None:
    source = _FETCH + _sibling(
        "        except Timeout:\n"
        "            raise\n"
        "        except Exception:\n"
        "            return []\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_interrupts_that_except_exception_never_catches(
    tmp_path: Path,
) -> None:
    source = (
        "class Fetcher:\n"
        "    def fetch(self, key):\n"
        "        try:\n"
        "            return self._client.get(key)\n"
        "        except asyncio.CancelledError:\n"
        "            raise\n"
        "        except BaseException:\n"
        "            return None\n"
    ) + _sibling(
        "        except Exception:\n"
        "            return []\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    exception=st.sampled_from(["QuotaExceeded", "errors.Fatal", "Stop"]),
    broad=st.sampled_from(["Exception", "BaseException", ""]),
    keeps_passthrough=st.booleans(),
)
def test_passthrough_property_flags_only_the_sibling_that_dropped_it(
    tmp_path: Path, exception: str, broad: str, keeps_passthrough: bool
) -> None:
    passthrough = f"        except {exception}:\n            raise\n"
    handler = f"except {broad}" if broad else "except"
    kept = passthrough if keeps_passthrough else ""
    source = (
        "class Fetcher:\n"
        "    def fetch(self, key):\n"
        "        try:\n"
        "            return self._client.get(key)\n"
        f"{passthrough}"
        "        except Exception:\n"
        "            return None\n"
        + _sibling(f"{kept}        {handler}:\n            return []\n")
    )
    shown = handler if broad else "a bare except"
    expected = [
        f"fetching.py:12: {shown} swallows {exception}, which fetch() in"
        f" this class lets through - add \"except {exception}: raise\""
        " above it"
    ]

    report = _report_for(tmp_path, source)

    assert report == ([] if keeps_passthrough else expected)


def test_survives_deeply_nested_code(tmp_path: Path) -> None:
    terms = " + ".join(f"term_{index}" for index in range(_DEEP_TERMS))
    source = f"def total():\n    return {terms}\n"

    assert _report_for(tmp_path, source) == []
