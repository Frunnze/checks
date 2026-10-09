from pathlib import Path

import pytest
from srp_support import (
    THRESHOLD,
    mixed_function,
    run_report,
    split_class,
    unit_named,
)


@pytest.mark.parametrize("suffix", [".py", ".ts", ".tsx"])
def test_a_class_reaching_two_outside_worlds_blocks(tmp_path, suffix):
    report = run_report(tmp_path, split_class(suffix), suffix)
    owner = unit_named(report, "<module>.Worker")

    assert report["failed"]
    assert owner["entities"] == ["filesystem", "network"]
    assert owner["coefficient"] >= THRESHOLD


@pytest.mark.parametrize("suffix", [".py", ".ts", ".tsx"])
def test_a_class_reaching_one_outside_world_passes(tmp_path, suffix):
    report = run_report(tmp_path, split_class(suffix, cohesive=True), suffix)
    owner = unit_named(report, "<module>.Worker")

    assert not report["failed"]
    assert owner["entities"] == ["network"]


@pytest.mark.parametrize("suffix", [".py", ".ts", ".tsx"])
def test_a_function_mixing_network_and_filesystem_blocks(tmp_path, suffix):
    report = run_report(tmp_path, mixed_function(suffix), suffix)
    unit = unit_named(report, "<module>.work")

    assert report["failed"]
    assert unit["entities"] == ["filesystem", "network"]


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_a_long_function_with_one_outside_world_passes(tmp_path, suffix):
    report = run_report(tmp_path, mixed_function(suffix, mixed=False), suffix)

    assert not report["failed"]
    assert unit_named(report, "<module>.work")["entities"] == ["network"]


def test_pure_helpers_without_operations_pass(tmp_path: Path):
    source = "\n".join(
        f"def utility_{i}(value):\n    result = value + {i}\n    return result\n"
        for i in range(10)
    )
    report = run_report(tmp_path, source)

    assert not report["failed"]
    assert unit_named(report, "<module>")["entities"] == []
