import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "unguarded-state-update" / "python"
    / "unguarded_state_updates.py"
)
_STATE_COLUMNS = ["status", "state", "phase", "stage", "step"]
_COLUMN_PREFIXES = ["", "order_", "payment_", "current_"]


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "orders.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="orders.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _message(line_number: int, column: str) -> str:
    return (
        f"orders.py:{line_number}: UPDATE sets {column} but its WHERE does"
        f" not test {column}, so it overwrites a concurrent change - add"
        f" AND {column} = <the state you read> to the WHERE and check the"
        " row count"
    )


def test_reports_a_status_write_without_compare_and_set(
    tmp_path: Path,
) -> None:
    source = (
        "def cancel(cursor, order_id):\n"
        "    cursor.execute(\n"
        '        """\n'
        "        UPDATE orders\n"
        "        SET status = 'cancelled', updated_at = NOW()\n"
        "        WHERE order_id = %s\n"
        '        """,\n'
        "        (order_id,),\n"
        "    )\n"
        "    return cursor.rowcount == 1\n"
    )

    assert _report_for(tmp_path, source) == [_message(3, "status")]


def test_reports_every_state_like_column_name(tmp_path: Path) -> None:
    source = (
        "SHIP = 'UPDATE parcels SET payment_status = %s WHERE id = %s'\n"
        "def move(connection, parcel_id, phase):\n"
        "    connection.execute(\n"
        "        'update ONLY public.parcels AS p set \"Phase\" = $1'\n"
        "        ' where p.id = $2', phase, parcel_id\n"
        "    )\n"
        "    connection.execute(\n"
        "        'UPDATE wizards SET current_step = :step WHERE id = :id'\n"
        "    )\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(1, "payment_status"),
        _message(4, "phase"),
        _message(8, "current_step"),
    ]


def test_reports_built_sql_and_updates_inside_statements(
    tmp_path: Path,
) -> None:
    source = (
        "def archive(cursor, table, ids):\n"
        "    cursor.execute(\n"
        "        f'UPDATE {table} SET state = %s ' + 'WHERE id = ANY(%s)',\n"
        "        ('archived', ids),\n"
        "    )\n"
        "    cursor.execute(\n"
        "        'WITH moved AS (UPDATE jobs SET stage = 2 FROM batches b'\n"
        "        ' WHERE jobs.batch_id = b.id RETURNING jobs.id)'\n"
        "        ' SELECT count(*) FROM moved'\n"
        "    )\n"
    )

    assert _report_for(tmp_path, source) == [
        _message(3, "state"),
        _message(7, "stage"),
    ]


def test_a_comment_in_the_where_is_not_a_guard(tmp_path: Path) -> None:
    source = (
        "QUERY = '''\n"
        "UPDATE jobs SET status = 'done'\n"
        "WHERE id = %s -- the caller already checked status\n"
        "'''\n"
    )

    assert _report_for(tmp_path, source) == [_message(1, "status")]


def test_passes_compare_and_set_shapes(tmp_path: Path) -> None:
    source = (
        "QUERIES = [\n"
        "    'UPDATE jobs SET status = %s WHERE id = %s AND status = %s',\n"
        "    \"UPDATE jobs SET status = 'x' WHERE id = 1"
        " AND status IN ('a', 'b')\",\n"
        "    \"UPDATE jobs SET status = 'x' WHERE id = 1"
        " AND j.status <> 'done'\",\n"
        "    'UPDATE jobs SET status = %s, version = version + 1'\n"
        "    ' WHERE id = %s AND version = %s',\n"
        "    \"UPDATE jobs SET status = CASE WHEN status = 'a'"
        " THEN 'b' ELSE status END WHERE id = %s\",\n"
        "    'UPDATE jobs SET step = step + 1 WHERE id = %s',\n"
        "    \"UPDATE jobs SET status = 'running' WHERE id = (SELECT id"
        " FROM jobs WHERE status = 'queued' FOR UPDATE SKIP LOCKED)\",\n"
        "]\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_what_is_not_a_state_write(tmp_path: Path) -> None:
    source = (
        "def store(cursor, where):\n"
        '    """UPDATE jobs SET status = 1 WHERE id = 2"""\n'
        "    cursor.execute('UPDATE jobs SET name = %s WHERE id = %s')\n"
        "    cursor.execute(\n"
        "        'INSERT INTO jobs (id, status) VALUES (%s, %s)'\n"
        "        ' ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status'\n"
        "        ' WHERE jobs.updated_at < NOW()'\n"
        "    )\n"
        "    cursor.execute('SELECT status FROM jobs FOR UPDATE')\n"
        "    cursor.execute('UPDATE jobs SET status = %s')\n"
        "    cursor.execute('UPDATE jobs SET status = 1 WHERE ' + where)\n"
        "    cursor.execute(f'UPDATE jobs SET status = 1 WHERE {where}')\n"
        "    cursor.execute('UPDATE jobs SET status_code = 1 WHERE id = 2')\n"
        "    return 'update the job set status where it is needed'\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    prefix=st.sampled_from(_COLUMN_PREFIXES),
    state_word=st.sampled_from(_STATE_COLUMNS),
    is_guarded=st.booleans(),
)
def test_state_property_flags_exactly_the_unguarded_write(
    tmp_path: Path, prefix: str, state_word: str, *, is_guarded: bool
) -> None:
    column = f"{prefix}{state_word}"
    guard = f" AND {column} = %s" if is_guarded else ""
    source = (
        "def move(cursor, row_id, old, new):\n"
        "    cursor.execute(\n"
        f"        'UPDATE rows SET {column} = %s WHERE id = %s{guard}',\n"
        "        (new, row_id, old),\n"
        "    )\n"
    )

    expected = [] if is_guarded else [_message(3, column)]

    assert _report_for(tmp_path, source) == expected
