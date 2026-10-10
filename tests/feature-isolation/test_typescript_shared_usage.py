from pathlib import Path

from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "feature-isolation" / "typescript" / "shared_usage.js"
_SHARED = "src/shared/ui/Meter.tsx"
_ALIASED_TSCONFIG = '{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}\n'


def _report_for(tmp_path: Path, files: dict[str, str]) -> list[str]:
    return report_from(_FINDER, tmp_path, files)


def test_allows_a_module_two_features_import(tmp_path: Path) -> None:
    files = {
        _SHARED: "export const Meter = 1;\n",
        "src/features/notes/NotePage.tsx": (
            'import { Meter } from "../../shared/ui/Meter";\n'
        ),
        "src/features/folder/FolderPage.tsx": (
            'import { Meter } from "../../shared/ui/Meter";\n'
        ),
    }

    assert _report_for(tmp_path, files) == []


def test_counts_an_import_through_a_path_alias(tmp_path: Path) -> None:
    tsconfig = tmp_path / "tsconfig.json"
    _ = tsconfig.write_text(_ALIASED_TSCONFIG, encoding="utf-8")
    meter = 'import { Meter } from "@/shared/ui/Meter";\n'
    files = {
        _SHARED: "export const Meter = 1;\n",
        "src/features/notes/NotePage.tsx": meter,
        "src/features/folder/FolderPage.tsx": meter,
    }

    assert _report_for(tmp_path, files) == []


def test_flags_a_module_only_one_feature_imports(tmp_path: Path) -> None:
    files = {
        _SHARED: "export const Meter = 1;\n",
        "src/features/notes/NotePage.tsx": (
            'import { Meter } from "../../shared/ui/Meter";\n'
        ),
    }

    assert _report_for(tmp_path, files) == [f"{_SHARED}: only notes imports it"]


def test_flags_a_module_no_feature_imports(tmp_path: Path) -> None:
    files = {_SHARED: "export const Meter = 1;\n"}

    assert _report_for(tmp_path, files) == [
        f"{_SHARED}: no feature imports it"
    ]


def test_keeps_a_module_the_app_shell_imports(tmp_path: Path) -> None:
    files = {
        _SHARED: "export const Meter = 1;\n",
        "src/App.tsx": 'import { Meter } from "./shared/ui/Meter";\n',
    }

    assert _report_for(tmp_path, files) == []


def test_keeps_a_module_another_shared_module_imports(
    tmp_path: Path,
) -> None:
    rail = "src/shared/ui/Rail.tsx"
    files = {
        _SHARED: "export const Meter = 1;\n",
        rail: 'import { Meter } from "./Meter";\n',
        "src/features/notes/NotePage.tsx": (
            'import { Rail } from "../../shared/ui/Rail";\n'
        ),
        "src/features/folder/FolderPage.tsx": (
            'import { Rail } from "../../shared/ui/Rail";\n'
        ),
    }

    assert _report_for(tmp_path, files) == []


def test_counts_a_nested_feature_under_its_own_feature(
    tmp_path: Path,
) -> None:
    files = {
        _SHARED: "export const Meter = 1;\n",
        "src/features/folder/FolderPage.tsx": (
            'import { Meter } from "../../shared/ui/Meter";\n'
        ),
        "src/features/folder/import/Flow.tsx": (
            'import { Meter } from "../../../shared/ui/Meter";\n'
        ),
    }

    assert _report_for(tmp_path, files) == [
        f"{_SHARED}: only folder imports it"
    ]


def test_allows_a_declaration_file_two_features_import(
    tmp_path: Path,
) -> None:
    files = {
        "src/shared/money.d.ts": "export interface Money { cents: number }\n",
        "src/features/cart/view.ts": (
            'import type { Money } from "../../shared/money";\n'
        ),
        "src/features/billing/view.ts": (
            'import type { Money } from "../../shared/money";\n'
        ),
    }

    assert _report_for(tmp_path, files) == []
