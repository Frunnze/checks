"""
The TypeScript feature-isolation finder must resolve a path alias with the
compiler options of the project that owns the importing file, wherever the
alias is configured. Domain: a sibling import spelled relative or through
the "@/*" alias, under a single tsconfig.json, a tsconfig.json that extends
a base, or the solution-style tsconfig.json Vite generates (no options of
its own, "references" to tsconfig.app.json, which holds "paths"). Oracle:
metamorphic - the alias spelling must be judged like its relative twin.

Concrete inputs -> expected outputs:
- input (single tsconfig.json with "paths": {"@/*": ["./src/*"]}):
      src/features/alpha/Page.tsx: import { api } from "@/features/beta/api";
  output: ["src/features/alpha/Page.tsx:1: features.beta"].
- input (falsifying example, pinned as @example):
      tsconfig.json: {"files": [], "references":
                      [{"path": "./tsconfig.app.json"},
                       {"path": "./tsconfig.node.json"}]}
      tsconfig.app.json: {"compilerOptions": {"paths":
                          {"@/*": ["./src/*"]}, ...}, "include": ["src"]}
      src/features/alpha/Page.tsx: import { api } from "@/features/beta/api";
  output: expected ["src/features/alpha/Page.tsx:1: features.beta"],
  got [] - the alias was resolved with the empty root options.
"""

import json
import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from typescript_finder_support import CHECKS, report_from

_FINDER = (
    CHECKS / "experimental" / "feature-isolation" / "typescript"
    / "feature_imports.js"
)
_IMPORTER = "src/features/alpha/Page.tsx"
_SIBLING = "src/features/beta/api.ts"
_SPECIFIERS = {"relative": "../beta/api", "alias": "@/features/beta/api"}
_SETTINGS = settings(max_examples=8, deadline=None)
_ALIASED_OPTIONS = {
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "baseUrl": ".",
    "paths": {"@/*": ["./src/*"]},
}
_NODE_OPTIONS = {"module": "ESNext", "moduleResolution": "bundler"}
_LAYOUTS = {
    "single": {
        "tsconfig.json": {
            "compilerOptions": _ALIASED_OPTIONS,
            "include": ["src"],
        },
    },
    "extends": {
        "tsconfig.base.json": {"compilerOptions": _ALIASED_OPTIONS},
        "tsconfig.json": {
            "extends": "./tsconfig.base.json",
            "include": ["src"],
        },
    },
    "solution": {
        "tsconfig.json": {
            "files": [],
            "references": [
                {"path": "./tsconfig.app.json"},
                {"path": "./tsconfig.node.json"},
            ],
        },
        "tsconfig.app.json": {
            "compilerOptions": _ALIASED_OPTIONS,
            "include": ["src"],
        },
        "tsconfig.node.json": {
            "compilerOptions": _NODE_OPTIONS,
            "include": ["vite.config.ts"],
        },
    },
}

layouts = st.sampled_from(sorted(_LAYOUTS))
spellings = st.sampled_from(sorted(_SPECIFIERS))


def _configured_files(layout: str, spelling: str) -> dict[str, str]:
    files: dict[str, str] = {}

    for name, configuration in _LAYOUTS[layout].items():
        files[name] = json.dumps(configuration)

    specifier = _SPECIFIERS[spelling]
    files[_IMPORTER] = f'import {{ api }} from "{specifier}";\n'
    files[_SIBLING] = "export const api = 1;\n"
    files["vite.config.ts"] = "export default {};\n"

    return files


@given(layout=layouts, spelling=spellings)
@example(layout="solution", spelling="alias")
@_SETTINGS
def test_feature_imports_property_judges_an_alias_like_its_relative_twin(
    layout: str, spelling: str
) -> None:
    files = _configured_files(layout, spelling)

    with tempfile.TemporaryDirectory() as directory:
        report = report_from(_FINDER, Path(directory), files)

    assert report == [f"{_IMPORTER}:1: features.beta"]
