"""
The Python strict-typing check must catch no_type_check however the
decorator is spelled. Domain: a function returning a str where an int is
declared, switched off by typing.no_type_check reached through a generated
import style, alias name and decorator spelling. Oracle: postcondition -
basedpyright skips such a function, so the silencer scan must fail the
gate and name the file.

Concrete inputs -> expected outputs:
- input:
      from typing import no_type_check

      @no_type_check
      def broken() -> int:
          return "text"
  output: exit 1, "user-service/src/broken.py:4:@no_type_check".
- input (falsifying example, pinned as @example):
      from typing import no_type_check as unchecked

      @unchecked
      def broken() -> int:
          return "text"
  output: expected exit 1, got exit 0 and "0 errors" - the alias hid the
  silencer from the scan and basedpyright skipped the function.
- input (falsifying example, pinned as @example): the same function under
  "@ no_type_check" (a space after @)
  output: expected exit 1, got exit 0.
"""

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from check_support import (
    link_real_python,
    link_toolkit_tool,
    repository,
    run_check,
    stage_file,
)

MODULE = "user-service/src/broken.py"
BROKEN = 'def broken() -> int:\n    return "text"\n'
IMPORTS = {
    "from_alias": "from {module} import no_type_check as {alias}\n",
    "assigned_alias": "import {module}\n\n{alias} = {module}.no_type_check\n",
    "plain": "from {module} import no_type_check\n",
    "attribute": "import {module}\n",
}
DECORATED = {
    "from_alias": "{alias}",
    "assigned_alias": "{alias}",
    "plain": "no_type_check",
    "attribute": "{module}.no_type_check",
}
SPELLINGS = ("@{}", "@ {}", "@({})", "@{}  # reviewed")


def _silenced_source(
    style: str, module: str, alias: str, spelling: str
) -> str:
    header = IMPORTS[style].format(module=module, alias=alias)
    decorator = DECORATED[style].format(module=module, alias=alias)

    return f"{header}\n\n{spelling.format(decorator)}\n{BROKEN}"


@given(
    style=st.sampled_from(sorted(IMPORTS)),
    module=st.sampled_from(("typing", "typing_extensions")),
    alias=st.sampled_from(("unchecked", "skip_types", "nt")),
    spelling=st.sampled_from(SPELLINGS),
)
@example(
    style="from_alias", module="typing", alias="unchecked", spelling="@{}"
)
@example(style="plain", module="typing", alias="unchecked", spelling="@ {}")
@settings(max_examples=4, deadline=None)
def test_silencer_property_catches_every_no_type_check_spelling(
    style: str, module: str, alias: str, spelling: str
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        repository(project)
        link_real_python(project)
        link_toolkit_tool(project, "basedpyright")
        stage_file(
            project, MODULE, _silenced_source(style, module, alias, spelling)
        )
        finished = run_check(project, "strict-typing")

    assert finished.returncode == 1, finished.stdout
    assert MODULE in finished.stderr
