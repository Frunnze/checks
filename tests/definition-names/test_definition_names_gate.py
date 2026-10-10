import subprocess
from pathlib import Path

from check_support import (
    COPIED_TOOLKIT,
    CheckRun,
    repository,
    run_check,
    stage_file,
)

TYPESCRIPT_FOLDER = "ui-service/src"
PYTHON_FOLDER = "user-service/src"
JOINED_DEFINITIONS = {
    "function": "export function loadAndSave(): void {}\n",
    "async_function": (
        "export async function loadAndSave(): Promise<void> {}\n"
    ),
    "generator_function": "export function* loadAndSave() {}\n",
    "default_function": "export default function loadAndSave() {}\n",
    "const_arrow": "export const loadAndSave = (): void => {};\n",
    "class": "export class LoadAndSave {}\n",
    "abstract_class": "export abstract class LoadAndSave {}\n",
    "default_class": "export default class LoadAndSave {}\n",
    "interface": "export interface LoadAndSave {}\n",
    "type_alias": "export type LoadAndSave = string;\n",
    "enum": 'export enum LoadAndSave { First = "first" }\n',
    "method": "export class Holder {\n  loadAndSave(): void {}\n}\n",
    "static_method": (
        "export class Holder {\n  static loadAndSave(): void {}\n}\n"
    ),
    "private_method": (
        "export class Holder {\n  private loadAndSave(): void {}\n}\n"
    ),
    "async_method": (
        "export class Holder {\n"
        "  async loadAndSave(): Promise<void> {}\n"
        "}\n"
    ),
    "generic_method": (
        "export class Holder {\n"
        "  loadAndSave<T>(item: T): T {\n"
        "    return item;\n"
        "  }\n"
        "}\n"
    ),
    "wrapped_parameters": (
        "export class Holder {\n"
        "  loadAndSave(\n"
        "    item: string,\n"
        "  ): void {}\n"
        "}\n"
    ),
    "arrow_property": (
        "export class Holder {\n  loadAndSave = (): void => {};\n}\n"
    ),
    "underscore_function": "export function _loadAndSave(): void {}\n",
    "underscore_class": "export class _LoadAndSave {}\n",
}
JOINED_CALLS = {
    "call_statement": (
        'import { loadAndSave } from "./library";\n\n'
        "export function caller(): void {\n  loadAndSave();\n}\n"
    ),
    "call_with_argument": (
        'import { loadAndSave } from "./library";\n\n'
        "export function caller(items: string[]): void {\n"
        "  loadAndSave(items);\n}\n"
    ),
}
OPERATOR_HOOKS = (
    "class Flags:\n"
    "    def __or__(self, other):\n"
    "        return self\n\n"
    "    def __and__(self, other):\n"
    "        return self\n"
)


def _reported_names(finished: CheckRun, folder: str) -> list[str]:
    names: list[str] = []

    for line in finished.stderr.splitlines():
        if line.startswith(f"{folder}/"):
            file_name = line.split(":", 1)[0].removeprefix(f"{folder}/")
            names.append(file_name.rsplit(".", 1)[0])

    return sorted(names)


def test_reports_every_typescript_definition_with_a_joined_name(
    tmp_path: Path,
) -> None:
    repository(tmp_path)

    for form, source in JOINED_DEFINITIONS.items():
        stage_file(tmp_path, f"{TYPESCRIPT_FOLDER}/{form}.ts", source)

    finished = run_check(tmp_path, "definition-names")

    assert _reported_names(finished, TYPESCRIPT_FOLDER) == sorted(
        JOINED_DEFINITIONS
    )


def test_never_reports_a_typescript_call_of_a_joined_name(
    tmp_path: Path,
) -> None:
    repository(tmp_path)

    for form, source in JOINED_CALLS.items():
        stage_file(tmp_path, f"{TYPESCRIPT_FOLDER}/{form}.ts", source)

    finished = run_check(tmp_path, "definition-names")

    assert finished.returncode == 0
    assert _reported_names(finished, TYPESCRIPT_FOLDER) == []


def test_never_reports_a_python_operator_hook(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, f"{PYTHON_FOLDER}/flags.py", OPERATOR_HOOKS)

    finished = run_check(tmp_path, "definition-names")

    assert finished.returncode == 0


def test_reports_a_python_joined_name_beside_a_non_utf8_byte(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    source_path = tmp_path / PYTHON_FOLDER / "legacy.py"
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(
        b"# -*- coding: latin-1 -*-\n"
        b"def load_and_save():  # caf\xe9\n"
        b"    return 1\n"
    )
    _ = (tmp_path / "checks.toml").write_text(
        f'source_directories = ["{PYTHON_FOLDER}"]\n'
        '[checks.definition-names]\nwhen = "pre-commit"\n',
        encoding="utf-8",
    )

    finished = subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "definition-names"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    assert finished.returncode == 1
    assert b"user-service/src/legacy.py:2:def load_and_save" in finished.stderr
