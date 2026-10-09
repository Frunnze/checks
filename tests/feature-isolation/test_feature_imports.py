import subprocess
import sys
from pathlib import Path

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_CHECKER = _CHECKS / "experimental" / "feature-isolation" / "python" / "feature_imports.py"
_OWN_FEATURE = Path("service/src/features/study_units")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    return _report_at(tmp_path, _OWN_FEATURE / "router.py", source)


def _report_at(tmp_path: Path, relative: Path, source: str) -> list[str]:
    module = tmp_path / relative
    module.parent.mkdir(parents=True, exist_ok=True)
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_CHECKER), "src"],
        input=str(relative),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_flags_an_import_from_a_sibling_feature(tmp_path: Path) -> None:
    report = _report_for(tmp_path, "from features.scheduling import due")

    assert report == [
        "service/src/features/study_units/router.py:1: features.scheduling"
    ]


def test_flags_a_plain_import_of_a_sibling_feature(tmp_path: Path) -> None:
    report = _report_for(tmp_path, "import features.scheduling.due")

    assert report == [
        "service/src/features/study_units/router.py:1: features.scheduling"
    ]


def test_flags_an_aliased_import_of_a_sibling_feature(
    tmp_path: Path,
) -> None:
    report = _report_for(tmp_path, "import features.scheduling.due as due")

    assert report == [
        "service/src/features/study_units/router.py:1: features.scheduling"
    ]


def test_allows_an_import_from_its_own_feature(tmp_path: Path) -> None:
    source = "from features.study_units.formatting import prepare\n"

    assert _report_for(tmp_path, source) == []


def test_allows_a_plain_import_of_its_own_feature(tmp_path: Path) -> None:
    assert _report_for(tmp_path, "import features.study_units.cards") == []


def test_allows_an_import_from_shared(tmp_path: Path) -> None:
    source = "from shared.models import Flashcard\n"

    assert _report_for(tmp_path, source) == []


def test_allows_a_third_party_import(tmp_path: Path) -> None:
    source = "import uuid\nfrom fastapi import APIRouter\n"

    assert _report_for(tmp_path, source) == []


def test_flags_a_relative_import_that_escapes_the_feature(
    tmp_path: Path,
) -> None:
    report = _report_for(tmp_path, "from ..scheduling import due")

    assert report == [
        "service/src/features/study_units/router.py:1: ..scheduling"
    ]


def test_allows_a_relative_import_inside_the_feature(
    tmp_path: Path,
) -> None:
    assert _report_for(tmp_path, "from .formatting import prepare") == []


def test_reports_every_crossing_in_a_file(tmp_path: Path) -> None:
    source = (
        "from features.scheduling import due\n"
        "from shared.models import Flashcard\n"
        "from features.file_system.storage import save\n"
    )
    report = _report_for(tmp_path, source)

    assert report == [
        "service/src/features/study_units/router.py:1: features.scheduling",
        "service/src/features/study_units/router.py:3: features.file_system",
    ]


def test_ignores_a_module_outside_any_feature(tmp_path: Path) -> None:
    report = _report_at(
        tmp_path,
        Path("service/src/shared/wiring.py"),
        "from features.scheduling import due",
    )

    assert report == []


def test_flags_an_import_from_a_sibling_subfeature(tmp_path: Path) -> None:
    (tmp_path / _OWN_FEATURE / "grading").mkdir(parents=True)
    report = _report_at(
        tmp_path,
        _OWN_FEATURE / "authoring" / "editor.py",
        "from features.study_units.grading.marks import score",
    )

    assert report == [
        "service/src/features/study_units/authoring/editor.py:1: "
        "features.study_units.grading"
    ]


def test_allows_a_subfeature_importing_from_its_parent(
    tmp_path: Path,
) -> None:
    report = _report_at(
        tmp_path,
        _OWN_FEATURE / "authoring" / "editor.py",
        "from features.study_units.formatting import prepare",
    )

    assert report == []


def test_allows_a_feature_importing_from_its_own_subfeature(
    tmp_path: Path,
) -> None:
    (tmp_path / _OWN_FEATURE / "authoring").mkdir(parents=True)
    report = _report_at(
        tmp_path,
        _OWN_FEATURE / "router.py",
        "from features.study_units.authoring.editor import edit",
    )

    assert report == []


def test_allows_a_module_beside_it_in_the_same_package(
    tmp_path: Path,
) -> None:
    report = _report_at(
        tmp_path,
        _OWN_FEATURE / "authoring" / "editor.py",
        "from features.study_units.authoring.marks import score",
    )

    assert report == []


def test_flags_a_deep_sibling_from_a_sibling_subfeature(
    tmp_path: Path,
) -> None:
    (tmp_path / _OWN_FEATURE / "grading" / "rules").mkdir(parents=True)
    report = _report_at(
        tmp_path,
        _OWN_FEATURE / "authoring" / "editor.py",
        "from features.study_units.grading.rules.marks import score",
    )

    assert report == [
        "service/src/features/study_units/authoring/editor.py:1: "
        "features.study_units.grading"
    ]


def test_says_nothing_about_a_self_contained_feature(
    tmp_path: Path,
) -> None:
    source = "from shared.database import SessionLocal\n"

    assert _report_for(tmp_path, source) == []
