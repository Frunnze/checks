import subprocess
import sys
from pathlib import Path

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_CHECKER = _CHECKS / "experimental" / "feature-isolation" / "python" / "shared_usage.py"


def _report_for(tmp_path: Path, files: dict[str, str]) -> list[str]:
    written: list[str] = []

    for relative, source in files.items():
        module = tmp_path / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")
        written.append(relative)

    finished = subprocess.run(
        [sys.executable, str(_CHECKER)],
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
