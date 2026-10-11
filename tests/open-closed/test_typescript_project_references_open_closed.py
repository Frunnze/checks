import json
from pathlib import Path

from typescript_finder_support import CHECKS, report_from

_TYPESCRIPT_CHECK = CHECKS / "experimental" / "open-closed" / "typescript"
_FINDER = _TYPESCRIPT_CHECK / "variant_dispatches.js"


def _write_solution_tsconfigs(root: Path) -> None:
    solution = {
        "files": [],
        "references": [
            {"path": "./tsconfig.app.json"},
            {"path": "./tsconfig.node.json"},
        ],
    }
    application = {
        "compilerOptions": {"paths": {"@/*": ["./src/*"]}},
        "include": ["src"],
    }
    tooling = {"include": ["vite.config.ts"]}
    configs = {
        "tsconfig.json": solution,
        "tsconfig.app.json": application,
        "tsconfig.node.json": tooling,
    }

    for name, config in configs.items():
        _ = (root / name).write_text(json.dumps(config), encoding="utf-8")


def test_flags_enum_dispatch_aliased_by_a_referenced_tsconfig(
    tmp_path: Path,
) -> None:
    _write_solution_tsconfigs(tmp_path)
    files = {
        "src/kinds.ts": (
            "export enum Kind { Deck = 'deck', File = 'file', Note = 'note' }\n"
        ),
        "src/route.ts": (
            "import { Kind } from '@/kinds';\n"
            "export function route(kind: Kind): number {\n"
            "  if (kind === Kind.Deck) return 0;\n"
            "  if (kind === Kind.File) return 1;\n"
            "  return kind === Kind.Note ? 2 : -1;\n"
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
            "src/route.ts:2: route compares kind to 3 enum members: "
            "Kind.Deck, Kind.File, Kind.Note"
        )
    ]
