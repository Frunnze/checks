import keyword
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_CHECKER = _CHECKS / "experimental" / "feature-isolation" / "python" / "shared_usage.py"
_NAMES = st.from_regex(r"[a-z]{3,8}", fullmatch=True).filter(
    lambda name: not keyword.iskeyword(name)
)
_FEATURE_NAMES = st.lists(_NAMES, min_size=1, max_size=3, unique=True)
_CANONICAL_SPELLING = "from shared.{module} import now\n"
_SPELLINGS = (
    "import shared.{module}\n",
    "import shared.{module} as {module}_alias\n",
    "from shared import {module}\n",
)


def _report_for(
    tmp_path: Path, files: dict[str, str], source_directory: str = "src"
) -> list[str]:
    written: list[str] = []

    for relative, source in files.items():
        module = tmp_path / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")
        written.append(relative)

    finished = subprocess.run(
        [sys.executable, str(_CHECKER), source_directory],
        input="\n".join(written),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_allows_a_module_two_features_import(tmp_path: Path) -> None:
    files = {
        "src/shared/clock.py": "def now():\n    return 1\n",
        "src/features/notes/router.py": "from shared.clock import now\n",
        "src/features/tests/router.py": "from shared.clock import now\n",
    }

    assert _report_for(tmp_path, files) == []


def test_flags_a_module_only_one_feature_imports(tmp_path: Path) -> None:
    files = {
        "src/shared/clock.py": "def now():\n    return 1\n",
        "src/features/notes/router.py": "from shared.clock import now\n",
    }
    report = _report_for(tmp_path, files)

    assert report == ["src/shared/clock.py: only notes imports it"]


def test_flags_a_module_no_feature_imports(tmp_path: Path) -> None:
    files = {
        "src/shared/clock.py": "def now():\n    return 1\n",
        "src/features/notes/router.py": "import uuid\n",
    }
    report = _report_for(tmp_path, files)

    assert report == ["src/shared/clock.py: no feature imports it"]


def test_allows_a_module_another_shared_module_uses(
    tmp_path: Path,
) -> None:
    files = {
        "src/shared/columns.py": "def column():\n    return 1\n",
        "src/shared/models.py": "from shared.columns import column\n",
        "src/features/notes/router.py": (
            "from shared.columns import column\nfrom shared.models import x\n"
        ),
        "src/features/tests/router.py": "from shared.models import x\n",
    }

    assert _report_for(tmp_path, files) == []


def test_allows_a_module_used_only_inside_shared(tmp_path: Path) -> None:
    files = {
        "src/shared/settings.py": "NAME = 'x'\n",
        "src/shared/celery_app.py": "from shared.settings import NAME\n",
        "src/features/notes/router.py": "from shared.celery_app import app\n",
        "src/features/tests/router.py": "from shared.celery_app import app\n",
    }

    assert _report_for(tmp_path, files) == []


def test_counts_a_plain_import_of_a_shared_module(tmp_path: Path) -> None:
    files = {
        "src/shared/clock.py": "def now():\n    return 1\n",
        "src/features/notes/router.py": "import shared.clock\n",
        "src/features/tests/router.py": "import shared.clock\n",
    }

    assert _report_for(tmp_path, files) == []


def test_resolves_a_nested_shared_module(tmp_path: Path) -> None:
    files = {
        "src/shared/models/columns.py": "def column():\n    return 1\n",
        "src/features/notes/router.py": (
            "from shared.models.columns import column\n"
        ),
    }
    report = _report_for(tmp_path, files)

    assert report == [
        "src/shared/models/columns.py: only notes imports it"
    ]


def test_reports_every_lonely_module_in_order(tmp_path: Path) -> None:
    files = {
        "src/shared/alpha.py": "A = 1\n",
        "src/shared/beta.py": "B = 2\n",
        "src/features/notes/router.py": (
            "from shared.alpha import A\nfrom shared.beta import B\n"
        ),
    }
    report = _report_for(tmp_path, files)

    assert report == [
        "src/shared/alpha.py: only notes imports it",
        "src/shared/beta.py: only notes imports it",
    ]


def test_reads_a_package_through_its_init(tmp_path: Path) -> None:
    files = {
        "src/shared/models/__init__.py": "from shared.models.folder import F\n",
        "src/shared/models/folder.py": "class F:\n    pass\n",
        "src/features/notes/router.py": "from shared.models import F\n",
        "src/features/tests/router.py": "from shared.models import F\n",
    }

    assert _report_for(tmp_path, files) == []


def _shared_tree(
    features: list[str], module: str, spelling: str
) -> dict[str, str]:
    files = {f"src/shared/{module}.py": "def now():\n    return 1\n"}

    for feature in features:
        files[f"src/features/{feature}/router.py"] = spelling.format(
            module=module
        )

    return files


def test_reads_a_path_with_a_space(tmp_path: Path) -> None:
    files = {
        "src/shared/my clock.py": "def now():\n    return 1\n",
        "src/features/notes/router.py": "import uuid\n",
    }
    report = _report_for(tmp_path, files)

    assert report == ["src/shared/my clock.py: no feature imports it"]


@pytest.mark.parametrize("spelling", _SPELLINGS)
@HYPOTHESIS_SETTINGS
@given(features=_FEATURE_NAMES, module=_NAMES)
def test_shared_usage_property_ignores_the_import_spelling(
    tmp_path: Path, spelling: str, features: list[str], module: str
) -> None:
    canonical = _shared_tree(features, module, _CANONICAL_SPELLING)
    variant = _shared_tree(features, module, spelling)

    assert _report_for(tmp_path, variant) == _report_for(tmp_path, canonical)


@HYPOTHESIS_SETTINGS
@given(features=_FEATURE_NAMES, module=_NAMES)
def test_shared_usage_property_an_empty_package_marker_adds_nothing(
    tmp_path: Path, features: list[str], module: str
) -> None:
    without_marker = _shared_tree(features, module, _CANONICAL_SPELLING)
    with_marker = {**without_marker, "src/shared/__init__.py": ""}

    assert _report_for(tmp_path, with_marker) == _report_for(
        tmp_path, without_marker
    )


def test_reads_a_source_folder_named_like_its_service(
    tmp_path: Path,
) -> None:
    files = {
        "app/app/shared/clock.py": "def now():\n    return 1\n",
        "app/app/features/notes/router.py": "from shared.clock import now\n",
    }
    report = _report_for(tmp_path, files, "app/app")

    assert report == ["app/app/shared/clock.py: only notes imports it"]


def test_a_features_folder_inside_shared_is_not_a_feature(
    tmp_path: Path,
) -> None:
    files = {
        "src/shared/clock.py": "def now():\n    return 1\n",
        "src/shared/features/toggles.py": "from shared.clock import now\n",
        "src/features/notes/router.py": (
            "from shared.features.toggles import on\n"
        ),
    }
    report = _report_for(tmp_path, files)

    assert report == ["src/shared/features/toggles.py: only notes imports it"]


def test_a_package_init_counts_every_import_from_its_package(
    tmp_path: Path,
) -> None:
    columns = "from shared.models.columns import column\n"
    clock = "from shared.clock import now\n"
    files = {
        "src/shared/models/__init__.py": "",
        "src/shared/models/columns.py": "def column():\n    return 1\n",
        "src/shared/clock.py": "def now():\n    return 1\n",
        "src/features/notes/router.py": columns + clock,
        "src/features/tasks/router.py": columns,
    }

    assert _report_for(tmp_path, files) == [
        "src/shared/clock.py: only notes imports it"
    ]


def test_counts_an_import_through_the_source_folder_as_a_package(
    tmp_path: Path,
) -> None:
    clock = "from src.shared.clock import now\n"
    files = {
        "svc/src/shared/clock.py": "def now():\n    return 1\n",
        "svc/src/features/notes/router.py": clock,
        "svc/src/features/tasks/router.py": clock,
    }

    assert _report_for(tmp_path, files, "svc/src") == []


def test_keeps_a_module_another_shared_module_imports_relatively(
    tmp_path: Path,
) -> None:
    user = "from shared.models.user import User\n"
    files = {
        "src/shared/models/base.py": "class Base:\n    pass\n",
        "src/shared/models/user.py": "from .base import Base\n",
        "src/features/notes/router.py": user,
        "src/features/tasks/router.py": user,
    }

    assert _report_for(tmp_path, files) == []
