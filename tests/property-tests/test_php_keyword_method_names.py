"""
PHP property-tests asks for a property test of every method, whatever its
name: since PHP 7 a method may be named like a keyword, and
token_get_all() reads such a name as the keyword token. Domain: one
untested method of svc/src/Repo.php named items or a keyword - list, new,
print, match, default, clone, empty, fn. Oracle: metamorphic - renaming
the method keeps the verdict of items().

Concrete inputs -> expected outputs:
- input: svc/src/Repo.php:
      final class Repo {
          public function items(): array { return [1]; }
      }
  output: exit 1, "items needs a property test".
- input (falsifying example): the same method named list()
  output: expected exit 1, "list needs a property test", got exit 0 - the
  name was read as T_LIST and skipped.
"""

from pathlib import Path

import pytest

from check_support import repository, run_configured, stage_file

CONFIGURATION = (
    'source_directories = ["svc/src", "svc/tests"]\nstable = "off"\n'
    '[checks.property-tests]\nwhen = "pre-commit"\n'
)
METHOD_NAMES = (
    "items",
    "list",
    "new",
    "print",
    "match",
    "default",
    "clone",
    "empty",
    "fn",
)


@pytest.mark.parametrize("name", METHOD_NAMES)
def test_every_method_needs_a_property_test(tmp_path: Path, name: str) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "svc/composer.json", '{"name": "acme/svc"}\n')
    stage_file(
        tmp_path,
        "svc/src/Repo.php",
        "<?php\nnamespace App;\nfinal class Repo {\n"
        f"    public function {name}(): array {{\n"
        "        return [1];\n    }\n}\n",
    )
    stage_file(
        tmp_path, "svc/tests/RepoTest.php", "<?php\nfinal class RepoTest {}\n"
    )

    finished = run_configured(tmp_path, CONFIGURATION, "property-tests")

    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert f"{name} needs a property test" in finished.stderr
