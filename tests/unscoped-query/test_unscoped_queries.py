import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "unscoped-query" / "python" / "unscoped_queries.py"
)
_ANY_ROW = "never filters by it, so any caller reaches any row"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "documents.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="documents.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _unscoped(line: int, function: str, owner: str) -> str:
    return (
        f"documents.py:{line}: {function}() receives {owner} but this query"
        f" {_ANY_ROW}"
    )


def test_reports_lookups_that_ignore_the_owner(tmp_path: Path) -> None:
    source = (
        "def get_document(cursor, document_id, user_id):\n"
        "    cursor.execute('SELECT * FROM documents WHERE id = %s',"
        " (document_id,))\n"
        "    return cursor.fetchone()\n"
        "async def delete_document(db, document_id, tenantId):\n"
        "    await db.execute(f'DELETE FROM docs WHERE id = {document_id}')\n"
    )

    assert _report_for(tmp_path, source) == [
        _unscoped(2, "get_document", "user_id"),
        _unscoped(5, "delete_document", "tenantId"),
    ]


def test_passes_scoped_and_ownerless_queries(tmp_path: Path) -> None:
    source = (
        "def get_owned(cursor, document_id, user_id):\n"
        "    cursor.execute(\n"
        "        'SELECT * FROM documents WHERE id = %s AND owner_id = %s',\n"
        "        (document_id, user_id),\n"
        "    )\n"
        "def get_by_user(cursor, user_id):\n"
        "    cursor.execute('SELECT * FROM t WHERE created_by = %s',"
        " (user_id,))\n"
        "def get_public(cursor, document_id):\n"
        "    cursor.execute('SELECT * FROM documents WHERE id = %s',"
        " (document_id,))\n"
        "def insert(cursor, user_id):\n"
        "    cursor.execute('INSERT INTO log VALUES (%s)', (user_id,))\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    owner=st.sampled_from(
        ["user_id", "owner_id", "account_id", "workspace_id", "orgId"]
    ),
    statement=st.sampled_from(
        [
            "SELECT * FROM items WHERE id = %s",
            "UPDATE items SET name = %s WHERE id = %s",
            "DELETE FROM items WHERE id = %s",
        ]
    ),
)
def test_owner_property_flags_every_spelling(
    tmp_path: Path, owner: str, statement: str
) -> None:
    source = (
        f"def change(cursor, item_id, {owner}):\n"
        f"    cursor.execute('{statement}', (item_id,))\n"
    )

    assert _report_for(tmp_path, source) == [_unscoped(2, "change", owner)]
