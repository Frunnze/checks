"""
Every file under a listed source folder is checked, whatever its subfolder
is called. Domain: one Python source folder svc/src and a generated
subfolder of it - plain names and the names some tools skip by default
(build, dist, vendor, at any depth) - holding either a 301-line module or
a silenced type error. Oracle: postcondition - file-length and
strict-typing must fail and name the file wherever it sits.

Concrete inputs -> expected outputs:
- input: svc/src/tools/module.py with 301 lines, file-length
  output: exit 1, "svc/src/tools/module.py (301 lines)".
- input (falsifying example, pinned as @example): svc/src/build/module.py
  with 301 lines, file-length
  output: expected exit 1, got exit 0 - the build folder was never listed.
- input (falsifying example, pinned as @example):
      svc/src/build/module.py:
          count: int = "three"  # pyright: ignore[reportAssignmentType]
  strict-typing
  output: expected exit 1 naming svc/src/build/module.py, got exit 0 -
  basedpyright honoured a silencer the scan never read.
"""

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from check_support import (
    link_real_python,
    link_toolkit_tool,
    repository,
    run_configured,
    stage_file,
)

CONFIGURATION = 'source_directories = ["svc/src"]\n'
SUBFOLDERS = ("tools", "build", "dist", "vendor", "app/build", "a/vendor/b")
BROKEN_SOURCES = {
    "file-length": "VALUE = 1\n" * 301,
    "strict-typing": (
        'count: int = "three"  # pyright: ignore[reportAssignmentType]\n'
    ),
}


@given(
    subfolder=st.sampled_from(SUBFOLDERS),
    gate=st.sampled_from(sorted(BROKEN_SOURCES)),
)
@example(subfolder="build", gate="file-length")
@example(subfolder="build", gate="strict-typing")
@settings(max_examples=6, deadline=None)
def test_gate_property_checks_every_subfolder_of_a_source_folder(
    subfolder: str, gate: str
) -> None:
    module = f"svc/src/{subfolder}/module.py"

    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        repository(project)
        link_real_python(project)
        link_toolkit_tool(project, "basedpyright")
        stage_file(project, "svc/src/main.py", "VALUE: int = 1\n")
        stage_file(project, module, BROKEN_SOURCES[gate])
        finished = run_configured(project, CONFIGURATION, gate)

    assert finished.returncode == 1, finished.stdout
    assert module in finished.stderr
