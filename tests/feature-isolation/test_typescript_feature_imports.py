from pathlib import Path

from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "feature-isolation" / "typescript" / "feature_imports.js"
_IMPORTER = "src/features/flashcards/Review.tsx"


def _report_for(tmp_path: Path, files: dict[str, str]) -> list[str]:
    return report_from(_FINDER, tmp_path, files)


def test_flags_an_import_from_a_sibling_feature(tmp_path: Path) -> None:
    files = {
        "src/features/chatbot/AskContext.tsx": "export const ask = 1;\n",
        _IMPORTER: 'import { ask } from "../chatbot/AskContext";\n',
    }

    assert _report_for(tmp_path, files) == [
        f"{_IMPORTER}:1: features.chatbot"
    ]


def test_flags_an_import_that_reaches_into_a_nested_sibling(
    tmp_path: Path,
) -> None:
    files = {
        "src/features/folder/import/api.ts": "export const start = 1;\n",
        _IMPORTER: 'import { start } from "../folder/import/api";\n',
    }

    assert _report_for(tmp_path, files) == [f"{_IMPORTER}:1: features.folder"]


def test_flags_a_type_only_import_from_a_sibling_feature(
    tmp_path: Path,
) -> None:
    files = {
        "src/features/notes/note-models.ts": "export type Note = string;\n",
        _IMPORTER: 'import type { Note } from "../notes/note-models";\n',
    }

    assert _report_for(tmp_path, files) == [f"{_IMPORTER}:1: features.notes"]


def test_allows_an_import_from_its_own_feature(tmp_path: Path) -> None:
    files = {
        "src/features/flashcards/queue.ts": "export const queue = 1;\n",
        _IMPORTER: 'import { queue } from "./queue";\n',
    }

    assert _report_for(tmp_path, files) == []


def test_allows_a_nested_feature_to_import_its_parent(
    tmp_path: Path,
) -> None:
    nested = "src/features/folder/import/Flow.tsx"
    files = {
        "src/features/folder/units-api.ts": "export const units = 1;\n",
        nested: 'import { units } from "../units-api";\n',
    }

    assert _report_for(tmp_path, files) == []


def test_allows_an_import_from_shared(tmp_path: Path) -> None:
    files = {
        "src/shared/api/http.ts": "export const get = 1;\n",
        _IMPORTER: 'import { get } from "../../shared/api/http";\n',
    }

    assert _report_for(tmp_path, files) == []


def test_ignores_a_package_import(tmp_path: Path) -> None:
    files = {_IMPORTER: 'import { For } from "solid-js";\n'}

    assert _report_for(tmp_path, files) == []


def test_reports_the_line_the_crossing_is_on(tmp_path: Path) -> None:
    files = {
        "src/features/chatbot/AskContext.tsx": "export const ask = 1;\n",
        _IMPORTER: (
            'import { For } from "solid-js";\n'
            "\n"
            'import { ask } from "../chatbot/AskContext";\n'
        ),
    }

    assert _report_for(tmp_path, files) == [
        f"{_IMPORTER}:3: features.chatbot"
    ]
