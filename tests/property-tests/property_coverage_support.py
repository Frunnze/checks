import subprocess
import sys
from pathlib import Path

CHECKS = Path(__file__).resolve().parents[2] / "checks"
CHECKER = CHECKS / "experimental" / "property-tests" / "python" / "property_test_coverage.py"
SOURCE = Path("service/src/features/study_units/scheduler.py")
TESTS = Path("service/tests/test_scheduler.py")


def report_for_files(tmp_path: Path, files: dict[str, str]) -> list[str]:
    written: list[str] = []

    for relative, source in files.items():
        written.append(_write(tmp_path, Path(relative), source))

    finished = subprocess.run(
        [sys.executable, str(CHECKER), "src"],
        input="\n".join(written),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def report_for(tmp_path: Path, source: str, tests: str) -> list[str]:
    return report_for_files(
        tmp_path, {str(SOURCE): source, str(TESTS): tests}
    )


def missing_in(source: str, name: str, line_number: int) -> str:
    return (
        f"{source}:{line_number}: {name} needs a property test "
        f"named test_{name}_property*"
    )


def missing(name: str, line_number: int) -> str:
    return missing_in(str(SOURCE), name, line_number)


def given_test(name: str, decorators: str = "@given()") -> str:
    return (
        "from hypothesis import given, settings\n"
        f"{decorators}\n"
        f"def {name}():\n"
        "    pass\n"
    )


def _write(tmp_path: Path, relative: Path, source: str) -> str:
    module = tmp_path / relative
    module.parent.mkdir(parents=True, exist_ok=True)
    _ = module.write_text(source, encoding="utf-8")

    return str(relative)
