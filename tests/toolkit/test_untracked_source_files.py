from pathlib import Path

from check_support import link_real_python, repository, run_check

NESTED_DEFINITION = (
    "def outer(value):\n"
    "    def inner(other):\n        return other\n"
    "    return inner(value)\n"
)
JOINED_NAME = "def load_and_save(value):\n    return value\n"


def _written(tmp_path: Path, relative: str, source: str) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(source, encoding="utf-8")


def test_nested_definitions_sees_a_file_never_added_to_git(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    _written(tmp_path, "user-service/src/nest.py", NESTED_DEFINITION)
    finished = run_check(tmp_path, "nested-definitions")

    assert finished.returncode == 1
    assert "inner" in finished.stderr


def test_definition_names_sees_a_file_never_added_to_git(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    _written(tmp_path, "user-service/src/joined.py", JOINED_NAME)
    finished = run_check(tmp_path, "definition-names")

    assert finished.returncode == 1
    assert "load_and_save" in finished.stderr


def test_property_tests_sees_a_file_never_added_to_git(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    _written(
        tmp_path,
        "user-service/src/plain.py",
        "def score(value):\n    return value\n",
    )
    finished = run_check(tmp_path, "property-tests")

    assert finished.returncode == 1
    assert "score needs a property test" in finished.stderr
