"""
Feature-isolation boundary across every import form Python allows.
Oracle: exact expected value, derived from the rule "one package chain
must be a prefix of the other", independent of how the import is spelled.

Concrete inputs -> expected outputs:
- input:
  service/src/features/study_units/router.py containing
      from features import scheduling
  with service/src/features/scheduling/ on disk
  output:
  "service/src/features/study_units/router.py:1: features.scheduling"
- input:
  service/src/features/study_units/authoring/editor.py containing
      from features.study_units import grading
  with service/src/features/study_units/grading/ on disk
  output:
  "service/src/features/study_units/authoring/editor.py:1:
   features.study_units.grading"
- input:
  service/src/features/study_units/authoring/editor.py containing
      from features.study_units import formatting
  with formatting.py a module, not a directory
  output:
  [] - a subfeature may read from its own parent package
- input:
  service/src/features/study_units/router.py containing
      import features.scheduling.due, features.file_system.storage
  output:
  both crossings reported, not only the first:
  ["...router.py:1: features.file_system",
   "...router.py:1: features.scheduling"]
"""

import subprocess
import sys
from pathlib import Path

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_CHECKER = _CHECKS / "experimental" / "feature-isolation" / "python" / "feature_imports.py"
_FEATURES = Path("service/src/features")


def _report(
    tmp_path: Path,
    relative: Path,
    source: str,
    packages: tuple[str, ...] = (),
) -> list[str]:
    for package in packages:
        (tmp_path / _FEATURES / package).mkdir(parents=True, exist_ok=True)

    module = tmp_path / relative
    module.parent.mkdir(parents=True, exist_ok=True)
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_CHECKER)],
        input=str(relative),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_flags_a_sibling_feature_taken_from_the_features_package(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "router.py",
        "from features import scheduling",
        packages=("scheduling",),
    )

    assert report == [
        "service/src/features/study_units/router.py:1: features.scheduling"
    ]


def test_flags_an_aliased_sibling_feature_from_the_features_package(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "router.py",
        "from features import scheduling as due_dates",
        packages=("scheduling",),
    )

    assert report == [
        "service/src/features/study_units/router.py:1: features.scheduling"
    ]


def test_allows_its_own_feature_taken_from_the_features_package(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "authoring" / "editor.py",
        "from features import study_units",
        packages=("study_units",),
    )

    assert report == []


def test_flags_a_sibling_subfeature_taken_from_its_parent_package(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "authoring" / "editor.py",
        "from features.study_units import grading",
        packages=("study_units/grading",),
    )

    assert report == [
        "service/src/features/study_units/authoring/editor.py:1: "
        "features.study_units.grading"
    ]


def test_allows_a_parent_module_taken_from_its_parent_package(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "authoring" / "editor.py",
        "from features.study_units import formatting",
    )

    assert report == []


def test_reports_every_sibling_in_one_import_statement(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "router.py",
        "import features.scheduling.due, features.file_system.storage",
        packages=("scheduling", "file_system"),
    )

    assert report == [
        "service/src/features/study_units/router.py:1: features.file_system",
        "service/src/features/study_units/router.py:1: features.scheduling",
    ]


def test_reports_every_sibling_named_in_one_from_import(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "router.py",
        "from features import scheduling, file_system",
        packages=("scheduling", "file_system"),
    )

    assert report == [
        "service/src/features/study_units/router.py:1: features.file_system",
        "service/src/features/study_units/router.py:1: features.scheduling",
    ]


def test_flags_a_sibling_feature_imported_inside_a_function(
    tmp_path: Path,
) -> None:
    source = "def load() -> None:\n    from features import scheduling\n"
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "router.py",
        source,
        packages=("scheduling",),
    )

    assert report == [
        "service/src/features/study_units/router.py:2: features.scheduling"
    ]


def test_allows_the_bare_features_package(tmp_path: Path) -> None:
    report = _report(
        tmp_path,
        _FEATURES / "study_units" / "router.py",
        "import features",
    )

    assert report == []
