"""
The import resolver terminates quickly on star-import packages: when a
package star-imports modules that are absent from the scan (generated
_pb2 modules, compiled extensions, untracked settings), when sibling
modules star-import each other, and when each module star-imports every
module below it. Domain: 2-4 absent star modules, 4-6 mutually
star-importing siblings, or 10-18 layered modules, each with a caller
reaching through the package. Oracle: the check ends inside a short
deadline with a report (exit 0), never runs on.

Concrete inputs -> expected outputs:
- input (pkg/_generated_0.py and pkg/_generated_1.py do not exist):
      pkg/__init__.py:
          from ._generated_0 import *
          from ._generated_1 import *
          from ._version import VERSION
          def version():
              return VERSION()
      app.py:
          from pkg import version
          def main():
              return version()
  output: exit 0 well inside 10 s (before the fix it never finished).
- input: pkg/m0.py ... pkg/m4.py each `from .mN import *` of all the
  others, pkg/__init__.py `from .m0 import *`, app.py calling
  `pkg.missing(x)`
  output: exit 0 well inside 10 s.
"""

import subprocess
import sys

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from srp_support import CHECK

TIMEOUT_SECONDS = 10
SIZES = {"absent": (2, 4), "mesh": (4, 6), "layered": (10, 18)}


@st.composite
def shapes(draw: st.DrawFn) -> tuple[str, int]:
    shape = draw(st.sampled_from(sorted(SIZES)))
    smallest, largest = SIZES[shape]
    return shape, draw(st.integers(smallest, largest))


def star_lines(modules: list[str]) -> str:
    return "".join(f"from .{module} import *\n" for module in modules)


def package_files(shape: str, size: int) -> dict[str, str]:
    if shape == "absent":
        generated = [f"_generated_{index}" for index in range(size)]
        return {
            "pkg/__init__.py": star_lines(generated)
            + "from ._version import VERSION\n\n\n"
            + "def version():\n    return VERSION()\n",
            "app.py": "from pkg import version\n\n\n"
            + "def main():\n    return version()\n",
        }
    files = {}
    for index in range(size):
        if shape == "layered":
            imported = [f"m{lower}" for lower in range(index)]
        else:
            imported = [f"m{other}" for other in range(size) if other != index]
        files[f"pkg/m{index}.py"] = (
            star_lines(imported) + f"\n\ndef helper_{index}(x):\n    return x\n"
        )
    top = f"m{size - 1}" if shape == "layered" else "m0"
    files["pkg/__init__.py"] = star_lines([top])
    files["app.py"] = "import pkg\n\n\ndef main(x):\n    return pkg.missing(x)\n"
    return files


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(shapes())
@example(("absent", 2))
@example(("mesh", 5))
@example(("layered", 18))
def test_star_import_packages_terminate_quickly(tmp_path_factory, case):
    shape, size = case
    root = tmp_path_factory.mktemp("stars")
    for relative, text in package_files(shape, size).items():
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(CHECK / "srp_check.py"), "--json", str(root)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError(
            f"{shape} package of {size} still analysed after "
            f"{TIMEOUT_SECONDS}s"
        ) from None

    assert result.returncode == 0, result.stderr
