from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.swallowed-passthrough]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, sibling_handlers: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/fetching.py",
        "class Fetcher:\n"
        "    def fetch(self, key):\n"
        "        try:\n"
        "            return self._client.get(key)\n"
        "        except QuotaExceeded:\n"
        "            raise\n"
        "        except Exception:\n"
        "            return None\n"
        "    def fetch_many(self, keys):\n"
        "        try:\n"
        "            return self._client.get_many(keys)\n"
        f"{sibling_handlers}"
        "        except Exception:\n"
        "            return []\n",
    )
    finished = run_configured(
        tmp_path, _CONFIGURATION, "swallowed-passthrough"
    )

    return finished.returncode, finished.stderr


def test_failure_names_the_swallowed_error(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/fetching.py:12: except Exception swallows"
        " QuotaExceeded, which fetch() in this class lets through"
        in stderr
    )
    assert "let them through" in stderr


def test_passes_a_sibling_that_keeps_the_passthrough(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(
        tmp_path, "        except QuotaExceeded:\n            raise\n"
    )

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(
        tmp_path, _CONFIGURATION, "swallowed-passthrough"
    )

    assert finished.returncode != 0
