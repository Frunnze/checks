from pathlib import Path

from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "open-closed" / "typescript" / "variant_dispatches.js"


def test_flags_one_axis_split_across_three_typed_registries(
    tmp_path: Path,
) -> None:
    files = {
        "src/models.ts": 'export type UnitType = "folder" | "file";\n',
        "src/api.ts": (
            'import type { UnitType } from "./models";\n'
            "const DELETE: Readonly<Record<UnitType, string>> = {\n"
            '  folder: "/folder", file: "/file"\n'
            "};\n"
        ),
        "src/view.ts": (
            'import type { UnitType } from "./models";\n'
            "const ICONS: Readonly<Record<UnitType, string>> = {\n"
            '  folder: "folder", file: "file"\n'
            "};\n"
            "const LINKS: Readonly<Record<UnitType, string>> = {\n"
            '  folder: "/folder", file: "/file"\n'
            "};\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
                "src/api.ts:2: UnitType behavior is split across 3 "
                "registries in 2 files: DELETE, ICONS, LINKS"
        )
    ]


def test_allows_two_small_presentation_maps(tmp_path: Path) -> None:
    files = {
        "src/models.ts": 'export type Tone = "good" | "bad";\n',
        "src/view.ts": (
            'import type { Tone } from "./models";\n'
            "const ICONS: Readonly<Record<Tone, string>> = {\n"
            '  good: "yes", bad: "no"\n'
            "};\n"
            "const CLASSES: Readonly<Record<Tone, string>> = {\n"
            '  good: "green", bad: "red"\n'
            "};\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == []


def test_flags_descriptor_array_split_from_inferred_behavior_map(
    tmp_path: Path,
) -> None:
    files = {
        "src/navigation.ts": (
            'type Destination = "inbox" | "archive" | "trash";\n'
            "const DESTINATIONS: readonly { name: Destination; label: string }[] = [\n"
            '  { name: "inbox", label: "Inbox" },\n'
            '  { name: "archive", label: "Archive" },\n'
            '  { name: "trash", label: "Trash" },\n'
            "];\n"
            "const PANELS = {\n"
            '  inbox: () => "inbox", archive: () => "archive", trash: () => "trash"\n'
            "};\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
            "src/navigation.ts:2: Destination behavior is split across 2 "
            "registries in 1 file: DESTINATIONS, PANELS"
        )
    ]


def test_does_not_treat_data_catalog_as_handler_registry(
    tmp_path: Path,
) -> None:
    files = {
        "src/catalog.ts": (
            'export type InputKind = "disk" | "http" | "memory";\n'
            "type Metadata = { readonly label: string };\n"
            "export const CATALOG: Readonly<Record<InputKind, Metadata>> = {\n"
            '  disk: { label: "Disk" },\n'
            '  http: { label: "HTTP" },\n'
            '  memory: { label: "Memory" },\n'
            "};\n"
        ),
        "src/workflow.ts": (
            'type Input = { readonly kind: "disk" | "http" | "memory" };\n'
            "export function read(input: Input): string {\n"
            '  return input.kind === "memory" ? "cached" : "external";\n'
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == []
