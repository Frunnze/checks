import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import FINDER_DIRECTORY

MEMORY_LIMIT = 256 * 2**20
PEAK_MEMORY_UNIT = 1 if sys.platform == "darwin" else 1024
CYCLE_MODULES = {
    "orders": ("notifications, payments", "PENDING = 'pending'"),
    "payments": ("notifications, orders", "CURRENCY = 'EUR'"),
    "notifications": ("orders, payments", "SENDER = 'shop@example.com'"),
}
FINDER_RUN = (
    "import resource, sys\n"
    "if sys.platform != 'darwin':\n"
    "    resource.setrlimit(resource.RLIMIT_AS, ({limit}, {limit}))\n"
    "sys.path.insert(0, {finder!r})\n"
    "from variant_dispatches import VariantDispatches\n"
    "print(len(VariantDispatches().find_in(sys.stdin.read().split())))\n"
    "print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)\n"
)


def _cycle_package(root: Path, helpers: int) -> list[str]:
    package = root / "shop"
    package.mkdir()
    _ = (package / "__init__.py").write_text("", encoding="utf-8")

    for name, (imported, constant) in CYCLE_MODULES.items():
        source = f"from . import {imported}\n\n{constant}\n"
        _ = (package / f"{name}.py").write_text(source, encoding="utf-8")

    for index in range(helpers):
        source = f"def helper_{index}(value):\n    return value + {index}\n"
        helper = package / f"helper_{index}.py"
        _ = helper.write_text(source, encoding="utf-8")

    return sorted(
        str(path.relative_to(root)) for path in package.glob("*.py")
    )


@given(helpers=st.integers(min_value=4, max_value=40))
@example(helpers=16)
@settings(max_examples=4, deadline=None)
def test_finder_property_resolves_an_import_cycle_in_bounded_memory(
    tmp_path_factory: pytest.TempPathFactory, helpers: int
) -> None:
    root = tmp_path_factory.mktemp("cycle")
    paths = _cycle_package(root, helpers)
    finder_run = FINDER_RUN.format(
        limit=MEMORY_LIMIT, finder=str(FINDER_DIRECTORY)
    )

    finished = subprocess.run(
        [sys.executable, "-c", finder_run],
        input="\n".join(paths),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert finished.returncode == 0, finished.stderr[-500:]

    finding_count, peak_memory = finished.stdout.split()

    assert finding_count == "0"
    assert int(peak_memory) * PEAK_MEMORY_UNIT <= MEMORY_LIMIT
