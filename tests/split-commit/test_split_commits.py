import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "split-commit" / "python" / "split_commits.py"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "orders.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="orders.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _split(line: int, receiver: str, final_line: int) -> str:
    return (
        f"orders.py:{line}: {receiver}.commit() saves part of the change -"
        f" the rest is committed on line {final_line}"
    )


def test_reports_a_commit_between_two_writes(tmp_path: Path) -> None:
    source = (
        "def transfer(connection, cursor, amount):\n"
        "    cursor.execute('UPDATE a SET balance = balance - %s', amount)\n"
        "    connection.commit()\n"
        "    cursor.execute('UPDATE b SET balance = balance + %s', amount)\n"
        "    connection.commit()\n"
    )

    assert _report_for(tmp_path, source) == [_split(3, "connection", 5)]


def test_reports_an_orm_session_and_an_awaited_commit(tmp_path: Path) -> None:
    source = (
        "async def place(session, order, item):\n"
        "    session.add(order)\n"
        "    await session.commit()\n"
        "    if item:\n"
        "        session.add(item)\n"
        "    await session.commit()\n"
    )

    assert _report_for(tmp_path, source) == [_split(3, "session", 6)]


def test_passes_one_commit_and_separate_transactions(tmp_path: Path) -> None:
    source = (
        "def save(connection, cursor, rows, other):\n"
        "    for row in rows:\n"
        "        cursor.execute('INSERT INTO t VALUES (%s)', row)\n"
        "        connection.commit()\n"
        "    cursor.execute('UPDATE t SET done = true')\n"
        "    other.commit()\n"
        "    connection.commit()\n"
        "    connection.commit()\n"
        "    if rows:\n"
        "        connection.commit()\n"
        "    else:\n"
        "        connection.commit()\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    receiver=st.sampled_from(["connection", "conn", "self.db", "session"]),
    write=st.sampled_from(["execute", "executemany", "add", "merge"]),
)
def test_receiver_property_flags_a_split_on_any_store(
    tmp_path: Path, receiver: str, write: str
) -> None:
    source = (
        "def change(self, connection, conn, session, record):\n"
        f"    {receiver}.{write}(record)\n"
        f"    {receiver}.commit()\n"
        f"    {receiver}.{write}(record)\n"
        f"    {receiver}.commit()\n"
    )

    assert _report_for(tmp_path, source) == [_split(3, receiver, 5)]
