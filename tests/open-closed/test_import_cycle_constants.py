"""
Modules that import each other must not make the constant resolution grow
without bound. Domain: a package whose orders, payments and notifications
modules import the other two by name and hold one string constant each,
beside 4-40 one-line helper modules. Oracle: a resource bound - the finder
answers within 256 MB and 20 s with no finding.

Concrete inputs -> expected outputs:
- input:
      shop/orders.py:        from . import notifications, payments
                             PENDING = 'pending'
      shop/payments.py:      from . import notifications, orders
                             CURRENCY = 'EUR'
      shop/notifications.py: from . import orders, payments
                             SENDER = 'shop@example.com'
      shop/helper_0.py ... shop/helper_15.py: def helper_<n>(value): ...
  output: expected no finding, got MemoryError - every pass prefixed the
  cycle's constants one level deeper (orders.payments.orders...), so each
  extra module doubled the memory.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import FINDER_DIRECTORY

MEMORY_LIMIT = 256 * 2**20
CYCLE_MODULES = {
    "orders": ("notifications, payments", "PENDING = 'pending'"),
    "payments": ("notifications, orders", "CURRENCY = 'EUR'"),
    "notifications": ("orders, payments", "SENDER = 'shop@example.com'"),
}
FINDER_RUN = (
    "import resource, sys\n"
    "resource.setrlimit(resource.RLIMIT_AS, ({limit}, {limit}))\n"
    "sys.path.insert(0, {finder!r})\n"
    "from variant_dispatches import VariantDispatches\n"
    "print(len(VariantDispatches().find_in(sys.stdin.read().split())))\n"
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
    assert finished.stdout.strip() == "0"
