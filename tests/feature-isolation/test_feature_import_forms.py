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

import keyword
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

from hypothesis import example, given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_CHECKER = _CHECKS / "experimental" / "feature-isolation" / "python" / "feature_imports.py"
_FEATURES = Path("service/src/features")
_NAMES = st.from_regex(r"[a-z]{3,8}", fullmatch=True).filter(
    lambda name: not keyword.iskeyword(name)
)


class _Layout(NamedTuple):
    importer: list[str]
    target: list[str]
    module: str


_PARENT_MODULE = _Layout(["units", "authoring"], ["units"], "formatting")


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
        [sys.executable, str(_CHECKER), "service/src"],
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


@st.composite
def _layouts(draw: st.DrawFn) -> _Layout:
    own = draw(_NAMES)
    other = draw(_NAMES.filter(lambda name: name != own))
    own_sub = draw(st.lists(_NAMES, max_size=2))
    target_feature = draw(st.sampled_from((own, other)))
    target_sub = draw(st.lists(_NAMES, max_size=2))

    if target_feature == own and draw(st.booleans()):
        target_sub = own_sub[: draw(st.integers(0, len(own_sub)))]

    target = [target_feature, *target_sub]

    return _Layout([own, *own_sub], target, draw(_NAMES))


def _relative_import(layout: _Layout) -> str:
    shared_depth = 0

    for mine, theirs in zip(layout.importer, layout.target, strict=False):
        if mine != theirs:
            break

        shared_depth += 1

    dots = "." * (len(layout.importer) - shared_depth + 1)
    module = ".".join([*layout.target[shared_depth:], layout.module])

    return f"from {dots}{module} import thing\n"


def _absolute_import(layout: _Layout) -> str:
    module = ".".join(["features", *layout.target, layout.module])

    return f"from {module} import thing\n"


@HYPOTHESIS_SETTINGS
@given(layout=_layouts())
@example(layout=_PARENT_MODULE)
def test_relative_import_property_judged_like_its_absolute_twin(
    layout: _Layout,
) -> None:
    importer = _FEATURES.joinpath(*layout.importer, "importer.py")
    packages = ("/".join(layout.target),)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        absolute = _report(root, importer, _absolute_import(layout), packages)
        relative = _report(root, importer, _relative_import(layout), packages)

    assert bool(relative) == bool(absolute)
