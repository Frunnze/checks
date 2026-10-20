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
    assert f"{name} needs 4 property tests" in finished.stderr
