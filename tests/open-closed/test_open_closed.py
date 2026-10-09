import subprocess
import sys
from pathlib import Path

from typescript_finder_support import CHECKS

_FINDER = CHECKS / "experimental" / "open-closed" / "python" / "variant_dispatches.py"
_MODULE = "service/src/features/units/presentation.py"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / _MODULE
    module.parent.mkdir(parents=True)
    _ = module.write_text(source, encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input=_MODULE,
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_flags_three_strings_compared_to_one_subject(
    tmp_path: Path,
) -> None:
    source = (
        "def href(unit):\n"
        "    if unit.kind == 'folder':\n        return '/folder'\n"
        "    if unit.kind == 'file':\n        return '/file'\n"
        "    if unit.kind != 'note':\n        return '/other'\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:1: href compares unit.kind to 3 strings: "
            "file, folder, note"
        )
    ]


def test_flags_three_string_patterns_for_one_subject(
    tmp_path: Path,
) -> None:
    source = (
        "def label(unit):\n"
        "    match unit.kind:\n"
        "        case 'folder' | 'file':\n            return 'document'\n"
        "        case 'note':\n            return 'note'\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:1: label compares unit.kind to 3 strings: "
            "file, folder, note"
        )
    ]


def test_allows_two_strings_for_one_subject(tmp_path: Path) -> None:
    source = (
        "def href(unit):\n"
        "    if unit.kind == 'folder':\n        return '/folder'\n"
        "    if unit.kind == 'file':\n        return '/file'\n"
    )

    assert _report_for(tmp_path, source) == []


def test_counts_each_string_only_once(tmp_path: Path) -> None:
    source = (
        "def href(unit):\n"
        "    if unit.kind == 'folder':\n        return '/folder'\n"
        "    if unit.kind != 'folder':\n        return '/other'\n"
        "    return '/folder' if 'file' == unit.kind else '/unknown'\n"
    )

    assert _report_for(tmp_path, source) == []


def test_does_not_combine_different_subjects(tmp_path: Path) -> None:
    source = (
        "def href(unit, source):\n"
        "    if unit.kind == 'folder':\n        return '/folder'\n"
        "    if unit.kind == 'file':\n        return '/file'\n"
        "    if source.kind == 'note':\n        return '/note'\n"
    )

    assert _report_for(tmp_path, source) == []


def test_treats_nested_functions_as_separate_scopes(
    tmp_path: Path,
) -> None:
    source = (
        "def outer(unit):\n"
        "    if unit.kind == 'folder':\n        return '/folder'\n"
        "    def inner():\n"
        "        if unit.kind == 'file':\n            return '/file'\n"
        "        if unit.kind == 'note':\n            return '/note'\n"
    )

    assert _report_for(tmp_path, source) == []


def test_flags_dispatch_across_concrete_domain_types(
    tmp_path: Path,
) -> None:
    source = (
        "def send(notification):\n"
        "    if isinstance(notification, Email):\n        return 'email'\n"
        "    if isinstance(notification, SMS):\n        return 'sms'\n"
        "    if type(notification) is Push:\n        return 'push'\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:1: send dispatches notification across 3 "
            "concrete types: Email, Push, SMS"
        )
    ]


def test_flags_class_patterns_as_concrete_type_dispatch(
    tmp_path: Path,
) -> None:
    source = (
        "def send(notification):\n"
        "    match notification:\n"
        "        case Email():\n            return 'email'\n"
        "        case SMS():\n            return 'sms'\n"
        "        case Push():\n            return 'push'\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:1: send dispatches notification across 3 "
            "concrete types: Email, Push, SMS"
        )
    ]


def test_ignores_primitive_runtime_validation(tmp_path: Path) -> None:
    source = (
        "def decode(value):\n"
        "    if isinstance(value, str):\n        return value\n"
        "    if isinstance(value, int):\n        return str(value)\n"
        "    if isinstance(value, bool):\n        return str(value)\n"
    )

    assert _report_for(tmp_path, source) == []


def test_does_not_flag_plain_composition(
    tmp_path: Path,
) -> None:
    source = (
        "def compose():\n"
        "    return Application(Database(), EventBus(), Clock())\n"
    )

    assert _report_for(tmp_path, source) == []
