import tempfile
from pathlib import Path

from typescript_finder_support import CHECKS, report_from

FINDER = CHECKS / "experimental" / "open-closed" / "typescript" / "variant_dispatches.js"


def typescript_findings(modules: dict[str, str]) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        return report_from(FINDER, Path(directory), modules)


def equality_chain(variants: list[str]) -> str:
    branches = "".join(
        f"  if (kind === '{variant}') return {index};\n"
        for index, variant in enumerate(variants)
    )

    return (
        "export function route(kind: string): number {\n"
        f"{branches}  return -1;\n}}\n"
    )


def or_chain(variants: list[str]) -> str:
    condition = " || ".join(f"kind === '{variant}'" for variant in variants)

    return (
        "export function route(kind: string): number {\n"
        f"  if ({condition}) return 1;\n"
        "  return -1;\n}\n"
    )


def includes_chain(variants: list[str]) -> str:
    values = ", ".join(f"'{variant}'" for variant in variants)

    return (
        "export function route(kind: string): number {\n"
        f"  if ([{values}].includes(kind)) return 1;\n"
        "  return -1;\n}\n"
    )


def switch_chain(variants: list[str]) -> str:
    cases = "".join(
        f"    case '{variant}': return {index};\n"
        for index, variant in enumerate(variants)
    )

    return (
        "export function route(kind: string): number {\n"
        f"  switch (kind) {{\n{cases}    default: return -1;\n  }}\n}}\n"
    )


def enum_chain(variants: list[str]) -> str:
    members = ", ".join(
        f"{variant.title()} = '{variant}'" for variant in variants
    )
    branches = "".join(
        f"  if (kind === Kind.{variant.title()}) return {index};\n"
        for index, variant in enumerate(variants)
    )

    return (
        f"export enum Kind {{ {members} }}\n"
        "export function route(kind: Kind): number {\n"
        f"{branches}  return -1;\n}}\n"
    )


def handler_registry(name: str, variants: list[str]) -> str:
    entries = ", ".join(f"{variant}: () => 1" for variant in variants)

    return f"export const {name} = {{ {entries} }};\n"


def label_registry(name: str, variants: list[str]) -> str:
    entries = ", ".join(
        f"{variant}: '{variant.title()}'" for variant in variants
    )

    return f"export const {name} = {{ {entries} }};\n"
