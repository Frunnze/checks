"""
Feature isolation judges the feature tree of each source folder; listing
the tests folder beside it, which coverage, api-contract and
property-tests require, must not change the verdict. Domain: a Python or
TypeScript service whose two features share svc/src/shared/clock, with or
without one feature reaching into the other, and a svc/tests folder.
Oracle: metamorphic - the gate gives the same exit code and findings with
source_directories ["svc/src"] and ["svc/src", "svc/tests"].

Concrete inputs -> expected outputs:
- input (python, no crossing):
      source_directories = ["svc/src"]
  output: exit code 0.
- input (falsifying example, pinned as @example):
      source_directories = ["svc/src", "svc/tests"]
      the same python service
  output: expected exit code 0, got 1 with
  "checks: svc/tests has no features folder - feature isolation needs
   svc/tests/features/<feature>/ for each feature".
- input (typescript, notes imports ../tasks/router):
      source_directories = ["svc/src", "svc/tests"]
  output: exit code 1 with
  "svc/src/features/notes/router.ts:2: features.tasks", never the
  missing-features-folder error.
"""

import tempfile
from pathlib import Path

from hypothesis import example, given
from hypothesis import strategies as st

from check_support import (
    HYPOTHESIS_SETTINGS,
    link_toolkit_node_modules,
    repository,
    run_configured,
    stage_file,
    stderr_lines,
)

_LISTINGS = ('["svc/src"]', '["svc/src", "svc/tests"]')
_PYTHON_CLOCK = "from shared.clock import now\n"
_PYTHON_CROSSING = "from features.tasks.router import later\n"
_TYPESCRIPT_CLOCK = 'import { now } from "../../shared/clock";\n'
_TYPESCRIPT_CROSSING = 'import { later } from "../tasks/router";\n'

languages = st.sampled_from(["python", "typescript"])


def _python_service(crossing: bool) -> dict[str, str]:
    notes = _PYTHON_CLOCK + (_PYTHON_CROSSING if crossing else "")

    return {
        "svc/src/shared/clock.py": "def now():\n    return 1\n",
        "svc/src/features/notes/router.py": notes,
        "svc/src/features/tasks/router.py": _PYTHON_CLOCK + "later = now\n",
        "svc/tests/test_router.py": "def test_router():\n    assert True\n",
    }


def _typescript_service(crossing: bool) -> dict[str, str]:
    notes = _TYPESCRIPT_CLOCK + (_TYPESCRIPT_CROSSING if crossing else "")

    return {
        "svc/src/shared/clock.ts": "export const now = 1;\n",
        "svc/src/features/notes/router.ts": notes,
        "svc/src/features/tasks/router.ts": (
            _TYPESCRIPT_CLOCK + "export const later = now;\n"
        ),
        "svc/tests/router.test.ts": 'test("router", () => 1);\n',
    }


def _verdicts(files: dict[str, str]) -> list[tuple[int, list[str]]]:
    verdicts: list[tuple[int, list[str]]] = []

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        repository(root)
        link_toolkit_node_modules(root)

        for relative, source in files.items():
            stage_file(root, relative, source)

        for listing in _LISTINGS:
            configuration = (
                f"source_directories = {listing}\n"
                '[checks.feature-isolation]\nwhen = "pre-commit"\n'
            )
            finished = run_configured(
                root, configuration, "feature-isolation"
            )
            verdicts.append((finished.returncode, stderr_lines(finished)))

    return verdicts


@given(language=languages, crossing=st.booleans())
@example(language="python", crossing=False)
@HYPOTHESIS_SETTINGS
def test_gate_property_listing_the_tests_folder_keeps_the_verdict(
    language: str, crossing: bool
) -> None:
    if language == "python":
        files = _python_service(crossing)
    else:
        files = _typescript_service(crossing)

    sources_only, with_tests = _verdicts(files)

    assert sources_only[0] == int(crossing)
    assert with_tests == sources_only
