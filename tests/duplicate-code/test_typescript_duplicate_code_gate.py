from pathlib import Path

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
)

COPIED_FUNCTION = (
    "export function total(values: number[]): number {\n"
    "  let sum = helper\n"
    "  for (const value of values) {\n"
    "    if (value > 100) {\n"
    "      sum += value * 2\n"
    "    } else if (value > 10) {\n"
    "      sum += value + 3\n"
    "    } else {\n"
    "      sum -= value\n"
    "    }\n"
    "  }\n"
    "  const rounded = Math.round(sum * 100) / 100\n"
    "  return rounded > 0 ? rounded : 0\n"
    "}\n"
)


def _module(name: str) -> str:
    return (
        'import { helper } from "./helper"\n\n'
        f"{COPIED_FUNCTION}\n"
        f"export function {name}(count: number): number {{\n"
        f"  let {name}Total = 0\n"
        f"  for (let step = 0; step < count; step += 1) {name}Total += step\n"
        f"  return {name}Total\n"
        "}\n"
    )


def _importing_module(name: str) -> str:
    imported_names = "".join(f"  helper{index},\n" for index in range(40))

    return (
        f'import {{\n{imported_names}}} from "./helpers";\n'
        f'import type {{ Shape }} from "./shapes";\n\n'
        f"export const {name}: Shape = helper0({name.upper()!r});\n"
    )


def test_passes_files_that_share_only_their_imports(tmp_path: Path) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, "ui-service/src/first.ts", _importing_module("first"))
    stage_file(
        tmp_path, "ui-service/src/second.ts", _importing_module("second")
    )

    finished = run_check(tmp_path, "duplicate-code")

    assert finished.returncode == 0, finished.stdout


def test_fails_on_a_copy_in_code_without_semicolons(tmp_path: Path) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, "ui-service/src/first.ts", _module("first"))
    stage_file(tmp_path, "ui-service/src/second.ts", _module("second"))

    finished = run_check(tmp_path, "duplicate-code")

    assert finished.returncode == 1
