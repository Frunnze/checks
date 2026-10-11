"""
The TypeScript feature-isolation finder must see a sibling import in every
form the TypeScript parser accepts, wherever it sits in the file. Domain:
one importer in features/alpha reaching src/features/beta/api.ts through a
generated import or re-export form, after generated valid code. Oracle:
metamorphic - an equivalent spelling of the same import, or harmless code
before it, must keep the verdict.

Concrete inputs -> expected outputs:
- input:
      src/features/alpha/page.tsx: import { api } from "../beta/api";
  output: ["src/features/alpha/page.tsx:1: features.beta"].
- input (falsifying example, pinned as @example):
      src/features/alpha/page.tsx: export * as ns from "../beta/api";
  output: expected ["src/features/alpha/page.tsx:1: features.beta"],
  got [] - the namespace re-export was never read.
- input (falsifying example, pinned as @example):
      src/features/alpha/page.tsx:
          const INLINE_CODE = /`([^`]+)`/g;
          export const Panel = lazy(() => import("../beta/api"));
  output: expected ["src/features/alpha/page.tsx:2: features.beta"],
  got [] - a backtick inside the regex hid every later import.
"""

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from typescript_finder_support import CHECKS, report_from

_FINDER = (
    CHECKS / "experimental" / "feature-isolation" / "typescript"
    / "feature_imports.js"
)
_IMPORTER = "src/features/alpha/page.tsx"
_SIBLING = "src/features/beta/api.ts"
_SPECIFIER = "../beta/api"
_SETTINGS = settings(max_examples=8, deadline=None)
_IMPORT_FORMS = [
    'import { api } from "{spec}";',
    'import * as ns from "{spec}";',
    'import type { Api } from "{spec}";',
    'import ns = require("{spec}");',
    'export { api } from "{spec}";',
    'export * from "{spec}";',
    'export * as ns from "{spec}";',
    'export type * as types from "{spec}";',
    'export const Panel = lazy(() => import("{spec}"));',
    'export const loaded = require("{spec}");',
    'export type Loaded = typeof import("{spec}");',
]
_CODE_BEFORE = [
    "",
    "const INLINE_CODE = /`([^`]+)`/g;\n",
    "export const Hint = () => <kbd>`</kbd>;\n",
    "export const label = `a ${1 + 1} b`;\n",
]

import_forms = st.sampled_from(_IMPORT_FORMS)
code_before = st.sampled_from(_CODE_BEFORE)


@given(form=import_forms, before=code_before)
@example(form='export * as ns from "{spec}";', before="")
@example(
    form='export const Panel = lazy(() => import("{spec}"));',
    before="const INLINE_CODE = /`([^`]+)`/g;\n",
)
@_SETTINGS
def test_feature_imports_property_reads_every_import_form(
    form: str, before: str
) -> None:
    importer = before + form.replace("{spec}", _SPECIFIER) + "\n"
    line_number = importer.count("\n")
    files = {
        _IMPORTER: importer,
        _SIBLING: "export const api = 1;\nexport type Api = number;\n",
    }

    with tempfile.TemporaryDirectory() as directory:
        report = report_from(_FINDER, Path(directory), files)

    assert report == [f"{_IMPORTER}:{line_number}: features.beta"]
