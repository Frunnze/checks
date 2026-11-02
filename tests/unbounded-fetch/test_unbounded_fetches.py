import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "unbounded-fetch" / "python" / "unbounded_fetches.py"
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


def _unbounded(line: int, fetch_line: int) -> str:
    return (
        f"orders.py:{line}: this ordered query has no LIMIT but line"
        f" {fetch_line} keeps only one row"
    )


def test_reports_latest_row_read_without_limit(tmp_path: Path) -> None:
    source = (
        "def latest(cursor, user_id):\n"
        "    cursor.execute(\n"
        "        'SELECT * FROM orders WHERE user_id = %s'\n"
        "        ' ORDER BY created_at DESC',\n"
        "        (user_id,),\n"
        "    )\n"
        "    return cursor.fetchone()\n"
    )

    assert _report_for(tmp_path, source) == [_unbounded(2, 7)]


def test_reports_a_constant_and_a_chained_first(tmp_path: Path) -> None:
    source = (
        "NEWEST = 'select id from events order by id desc'\n"
        "async def newest(connection, session):\n"
        "    cursor = await connection.execute(NEWEST)\n"
        "    row = await cursor.fetchone()\n"
        "    return row, session.execute(text(NEWEST)).first()\n"
    )

    assert _report_for(tmp_path, source) == [
        _unbounded(3, 4),
        _unbounded(5, 5),
    ]


def test_passes_limited_and_unordered_queries(tmp_path: Path) -> None:
    source = (
        "def read(cursor, user_id):\n"
        "    cursor.execute('SELECT * FROM t ORDER BY id DESC LIMIT 1')\n"
        "    first = cursor.fetchone()\n"
        "    cursor.execute('SELECT * FROM t WHERE id = %s', (user_id,))\n"
        "    second = cursor.fetchone()\n"
        "    cursor.execute('SELECT * FROM t ORDER BY id')\n"
        "    return first, second, cursor.fetchall()\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    fetch=st.sampled_from(["fetchone", "first", "scalar", "one_or_none"]),
    bound=st.sampled_from(
        ["LIMIT 1", "limit %s", "FETCH FIRST 1 ROWS ONLY", "fetch next 1"]
    ),
)
def test_limit_property_passes_every_row_limit(
    tmp_path: Path, fetch: str, bound: str
) -> None:
    source = (
        "def pick(cursor):\n"
        "    cursor.execute('SELECT id FROM t ORDER BY id')\n"
        f"    cursor.{fetch}()\n"
        f"    cursor.execute('SELECT id FROM t ORDER BY id {bound}')\n"
        f"    return cursor.{fetch}()\n"
    )

    assert _report_for(tmp_path, source) == [_unbounded(2, 3)]
