import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "narrow-cleanup-handler" / "python"
    / "narrow_cleanup_handlers.py"
)
_FIX = " - catch BaseException or move the cleanup to finally"
_CLEANUPS = ("release", "unlock", "rollback", "close", "unlink", "cancel")
_SPECIFIC_TYPES = ("ValueError", "KeyError", "LookupError", "QuotaExceeded")
_BROAD_TYPES = ("Exception", "BaseException", "builtins.BaseException")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "jobs.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="jobs.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _expected(line: int, caught: str, cleanup: str) -> str:
    return (
        f"jobs.py:{line}: except {caught} runs {cleanup}() and re-raises,"
        f" but any other exception skips it{_FIX}"
    )


def test_reports_a_lock_released_only_for_one_error(tmp_path: Path) -> None:
    source = (
        "class Jobs:\n"
        "    def submit(self, job):\n"
        "        if not self._acquire_job_lock(job.key):\n"
        "            raise RuntimeError(job.key)\n"
        "        try:\n"
        "            self._store.save(job)\n"
        "        except LookupError:\n"
        "            self._release_job_lock(job.key)\n"
        "            raise\n"
    )

    assert _report_for(tmp_path, source) == [
        _expected(7, "LookupError", "_release_job_lock")
    ]


def test_reports_a_transaction_rolled_back_for_listed_errors(
    tmp_path: Path,
) -> None:
    source = (
        "def transfer(connection, amount):\n"
        "    connection.execute('BEGIN')\n"
        "    try:\n"
        "        connection.execute('UPDATE accounts', amount)\n"
        "        connection.commit()\n"
        "    except (ValueError, db.IntegrityError) as error:\n"
        "        logger.warning('transfer failed')\n"
        "        connection.rollback()\n"
        "        raise error\n"
    )

    assert _report_for(tmp_path, source) == [
        _expected(6, "ValueError, db.IntegrityError", "rollback")
    ]


def test_reports_a_temporary_file_removed_for_one_error(
    tmp_path: Path,
) -> None:
    source = (
        "import os\n"
        "import tempfile\n"
        "async def export(rows):\n"
        "    handle, path = tempfile.mkstemp()\n"
        "    try:\n"
        "        await write_rows(handle, rows)\n"
        "    except UnicodeEncodeError:\n"
        "        os.unlink(path)\n"
        "        raise\n"
        "    return path\n"
    )

    assert _report_for(tmp_path, source) == [
        _expected(7, "UnicodeEncodeError", "unlink")
    ]


def test_reports_best_effort_cleanup_inside_the_handler(
    tmp_path: Path,
) -> None:
    source = (
        "import contextlib\n"
        "async def publish(broker, message):\n"
        "    channel = await broker.open_channel()\n"
        "    try:\n"
        "        await channel.send(message)\n"
        "    except TimeoutError:\n"
        "        raise\n"
        "    except broker.Rejected:\n"
        "        with contextlib.suppress(Exception):\n"
        "            await channel.aclose()\n"
        "        raise\n"
    )

    assert _report_for(tmp_path, source) == [
        _expected(8, "broker.Rejected", "aclose")
    ]


def test_passes_cleanup_that_runs_for_every_error(tmp_path: Path) -> None:
    source = (
        "def first(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        lock.release()\n"
        "        raise\n"
        "def second(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except:\n"
        "        lock.release()\n"
        "        raise\n"
        "def third(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except ValueError:\n"
        "        lock.release()\n"
        "        raise\n"
        "    finally:\n"
        "        audit()\n"
        "def fourth(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except ValueError:\n"
        "        lock.release()\n"
        "        raise\n"
        "    except BaseException:\n"
        "        lock.release()\n"
        "        raise\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_handlers_that_end_the_error_or_clean_nothing(
    tmp_path: Path,
) -> None:
    source = (
        "def translated(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except KeyError as error:\n"
        "        lock.release()\n"
        "        raise LookupError('missing') from error\n"
        "def swallowed(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except KeyError:\n"
        "        lock.release()\n"
        "        return None\n"
        "def logged(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except KeyError:\n"
        "        logger.exception('work failed')\n"
        "        raise\n"
        "def recovered(lock):\n"
        "    lock.acquire()\n"
        "    try:\n"
        "        work()\n"
        "    except KeyError as error:\n"
        "        if error.args:\n"
        "            lock.release()\n"
        "            return None\n"
        "        raise\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_cleanup_tied_to_the_failure_itself(tmp_path: Path) -> None:
    source = (
        "import asyncio\n"
        "import socket\n"
        "async def relay(coroutine):\n"
        "    task = asyncio.create_task(coroutine)\n"
        "    try:\n"
        "        return await task\n"
        "    except asyncio.CancelledError:\n"
        "        task.cancel()\n"
        "        raise\n"
        "def dial(address):\n"
        "    connection = socket.create_connection(address, timeout=5)\n"
        "    try:\n"
        "        connection.sendall(b'hello')\n"
        "    except (OSError, socket.timeout):\n"
        "        connection.close()\n"
        "        raise\n"
        "    return connection\n"
        "class Client:\n"
        "    def send(self, frame):\n"
        "        try:\n"
        "            self._transport.write(frame)\n"
        "        except ProtocolError:\n"
        "            self.close()\n"
        "            raise\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    cleanup=st.sampled_from(_CLEANUPS),
    caught=st.sampled_from(_SPECIFIC_TYPES + _BROAD_TYPES),
)
def test_narrow_property_flags_only_specific_types(
    tmp_path: Path, cleanup: str, caught: str
) -> None:
    source = (
        "def run(resource):\n"
        "    resource.open()\n"
        "    try:\n"
        "        resource.process()\n"
        f"    except {caught}:\n"
        f"        resource.{cleanup}()\n"
        "        raise\n"
    )

    report = _report_for(tmp_path, source)

    if caught in _SPECIFIC_TYPES:
        assert report == [_expected(5, caught, cleanup)]
    else:
        assert report == []
