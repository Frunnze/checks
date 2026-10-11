import subprocess
from pathlib import Path

import pytest
from check_support import (
    link_real_python,
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
    stderr_lines,
)

_PYTHON = "user-service/src"
_TYPESCRIPT = "ui-service/src"
_REGISTRY_REPORT = (
    "variant behavior is split across 2 registries in 2 files: "
    "HANDLERS, LABELS"
)
_SCATTERED_REPORT = (
    "ImportRequest.kind dispatch is scattered across 2 functions in 2 "
    "files: file, link, text"
)
_IMPORT_REQUEST = (
    'import type { ImportRequest } from "./models";\n'
)
_DECLINED = "Payment was declined by the bank"
_SHAPES = {
    "python error text producer": (
        {
            f"{_PYTHON}/a_client.py": (
                f"def retry(text):\n    return text == {_DECLINED!r}\n"
            ),
        },
        f"{_PYTHON}/z_server.py",
        f"def register():\n    raise ValueError({_DECLINED!r})\n",
        (
            f'{_PYTHON}/z_server.py:2: produces human-readable error text '
            f'"{_DECLINED}" branched on at {_PYTHON}/a_client.py:2; use a '
            "stable error code and handler registry"
        ),
    ),
    "python registries": (
        {
            f"{_PYTHON}/a_labels.py": (
                "LABELS = {'deck': 'Deck', 'file': 'File', 'note': 'Note'}\n"
            ),
        },
        f"{_PYTHON}/z_handlers.py",
        (
            "def open_deck(): ...\n"
            "def open_file(): ...\n"
            "def open_note(): ...\n"
            "HANDLERS = {\n"
            "    'deck': open_deck, 'file': open_file, 'note': open_note\n"
            "}\n"
        ),
        f"{_PYTHON}/z_handlers.py:4: {_REGISTRY_REPORT}",
    ),
    "typescript registries": (
        {
            f"{_TYPESCRIPT}/a_labels.ts": (
                "export const LABELS = {\n"
                "  deck: 'Deck', file: 'File', note: 'Note'\n"
                "};\n"
            ),
        },
        f"{_TYPESCRIPT}/z_handlers.ts",
        (
            "export const HANDLERS = {\n"
            "  deck: () => 1, file: () => 2, note: () => 3\n"
            "};\n"
        ),
        f"{_TYPESCRIPT}/z_handlers.ts:1: {_REGISTRY_REPORT}",
    ),
    "typescript scattered dispatch": (
        {
            f"{_TYPESCRIPT}/models.ts": (
                "export type ImportRequest = {\n"
                '  readonly kind: "file" | "link" | "text";\n'
                "};\n"
            ),
            f"{_TYPESCRIPT}/a_label.ts": (
                f"{_IMPORT_REQUEST}"
                "export function label(request: ImportRequest): string {\n"
                '  if (request.kind === "file") return "File";\n'
                '  return request.kind === "link" ? "Link" : "Text";\n'
                "}\n"
            ),
        },
        f"{_TYPESCRIPT}/z_origin.ts",
        (
            f"{_IMPORT_REQUEST}"
            "export function origin(request: ImportRequest): string {\n"
            '  return request.kind === "text" ? "typed" : "external";\n'
            "}\n"
        ),
        f"{_TYPESCRIPT}/z_origin.ts:2: {_SCATTERED_REPORT}",
    ),
}


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_changed_scope_fails_a_later_file_joining_a_cross_file_finding(
    tmp_path: Path, shape: str
) -> None:
    committed, staged_path, staged_source, report = _SHAPES[shape]
    repository(tmp_path)
    link_real_python(tmp_path)
    link_toolkit_node_modules(tmp_path)

    for relative, source in committed.items():
        stage_file(tmp_path, relative, source)

    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "existing"],
        cwd=tmp_path,
        check=True,
    )
    stage_file(tmp_path, staged_path, staged_source)
    finished = run_check(
        tmp_path, "open-closed", {"open-closed": 'scope = "changed"\n'}
    )

    assert finished.returncode == 1
    assert report in stderr_lines(finished)
