from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unscoped-query]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, scope: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/documents.py",
        "def get_document(cursor, document_id, user_id):\n"
        f"    cursor.execute('SELECT * FROM docs WHERE id = %s{scope}',\n"
        f"                   (document_id{', user_id' if scope else ''}))\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unscoped-query")

    return finished.returncode, finished.stderr


def test_failure_names_the_function_and_owner(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/documents.py:2: get_document() receives user_id"
        in stderr
    )


def test_passes_a_query_scoped_to_the_owner(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, " AND user_id = %s")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unscoped-query")

    assert finished.returncode != 0
