import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "unraised-exception" / "python" / "unraised_exceptions.py"
)


def _report_for(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for relative, source in files.items():
        module = tmp_path / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(files),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _unraised(path: str, line: int, exception: str) -> str:
    return f"{path}:{line}: {exception}(...) is built but never raised"


def test_reports_imported_and_discarded_exceptions(tmp_path: Path) -> None:
    source = (
        "from web import HTTPException\n"
        "def check(owner, user, limit, used):\n"
        "    if owner != user:\n"
        "        HTTPException(status_code=403)\n"
        "    if used > limit:\n"
        "        _ = errors.QuotaExceeded('over the limit')\n"
        "    if not owner:\n"
        "        ValueError('missing owner')\n"
    )
    errors = (
        "class Problem(Exception):\n    pass\n"
        "class QuotaExceeded(Problem):\n    pass\n"
    )
    files = {"guard.py": source, "errors.py": errors}

    assert _report_for(tmp_path, files) == [
        f"{_unraised('guard.py', 4, 'HTTPException')} - add raise",
        f"{_unraised('guard.py', 6, 'errors.QuotaExceeded')} - add raise",
        f"{_unraised('guard.py', 8, 'ValueError')} - add raise",
    ]


def test_passes_raised_kept_and_logged_errors(tmp_path: Path) -> None:
    source = (
        "import logging\n"
        "import warnings\n"
        "def check(value, parser):\n"
        "    if value < 0:\n        raise ValueError(value)\n"
        "    error = ValueError(value)\n"
        "    logging.error('bad value %s', value)\n"
        "    parser.error('bad value')\n"
        "    warnings.warn(DeprecationWarning('old'))\n"
        "    DeprecationWarning('emitted on its own')\n"
        "    return error\n"
    )

    assert _report_for(tmp_path, {"check.py": source}) == []


def test_skips_test_files(tmp_path: Path) -> None:
    source = "def test_error():\n    ValueError('built to inspect')\n"

    report = _report_for(tmp_path, {"tests/test_errors.py": source})

    assert report == []


@HYPOTHESIS_SETTINGS
@given(
    name=st.from_regex(r"[A-Z][a-z]{2,8}", fullmatch=True),
    suffix=st.sampled_from(["Error", "Exception", "Exit", "Interrupt"]),
)
def test_name_property_flags_every_exception_name(
    tmp_path: Path, name: str, suffix: str
) -> None:
    exception = f"{name}{suffix}"
    source = (
        "def guard(ok):\n"
        f"    if not ok:\n        {exception}('stop')\n"
        f"    {name.lower()}{suffix}('a function, not a class')\n"
    )

    assert _report_for(tmp_path, {"guard.py": source}) == [
        f"{_unraised('guard.py', 3, exception)} - add raise"
    ]
