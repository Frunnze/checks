from pathlib import Path

import pytest

from check_support import repository, run_configured, stage_file

CONFIGURATION = (
    'source_directories = ["svc/src", "svc/tests"]\nstable = "off"\n'
    '[checks.property-tests]\nwhen = "pre-commit"\n'
)
MINIMUM_PROPERTY_TESTS = 4


def _property_test_class(test_names: list[str]) -> str:
    methods: list[str] = []

    for test_name in test_names:
        methods.append(
            f"    public function {test_name}(): void {{\n"
            "        $this->forAll();\n    }\n"
        )

    return "<?php\nfinal class RepoTest {\n" + "".join(methods) + "}\n"


def _staged_package(tmp_path: Path, test_files: dict[str, str]) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "svc/composer.json", '{"name": "acme/svc"}\n')
    stage_file(
        tmp_path,
        "svc/src/Repo.php",
        "<?php\nnamespace App;\nfinal class Repo {\n"
        "    public function items(): array {\n"
        "        return [1];\n    }\n}\n",
    )

    for relative, source in test_files.items():
        stage_file(tmp_path, relative, source)


@pytest.mark.parametrize("test_count", range(MINIMUM_PROPERTY_TESTS + 2))
def test_a_method_needs_four_property_tests(
    tmp_path: Path, test_count: int
) -> None:
    test_names: list[str] = []

    for number in range(test_count):
        test_names.append(f"test_items_property_{number}")

    _staged_package(
        tmp_path, {"svc/tests/RepoTest.php": _property_test_class(test_names)}
    )
    finished = run_configured(tmp_path, CONFIGURATION, "property-tests")

    if test_count < MINIMUM_PROPERTY_TESTS:
        assert finished.returncode == 1, finished.stdout + finished.stderr
        assert "items needs 4 property tests" in finished.stderr
    else:
        assert finished.returncode == 0, finished.stdout + finished.stderr


def test_one_test_name_in_four_test_files_counts_once(tmp_path: Path) -> None:
    repeated = _property_test_class(["test_items_property_is_a_list"])
    test_files: dict[str, str] = {}

    for number in range(MINIMUM_PROPERTY_TESTS):
        test_files[f"svc/tests/Repo{number}Test.php"] = repeated

    _staged_package(tmp_path, test_files)
    finished = run_configured(tmp_path, CONFIGURATION, "property-tests")

    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert "items needs 4 property tests" in finished.stderr
