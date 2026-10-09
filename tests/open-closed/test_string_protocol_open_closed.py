import subprocess
import sys
from pathlib import Path

from typescript_finder_support import CHECKS

_FINDER = CHECKS / "experimental" / "open-closed" / "python" / "protocol_strings.py"


def report_from(tmp_path: Path, files: dict[str, str]) -> list[str]:
    paths: list[str] = []

    for relative, source in files.items():
        module = tmp_path / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")
        paths.append(relative)

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(paths),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_flags_behavior_selected_by_python_response_text_in_typescript(
    tmp_path: Path,
) -> None:
    files = {
        "server/account.py": (
            "def register():\n"
            "    return JsonResponse(content='Account name already exists')\n"
        ),
        "web/account.ts": (
            "export function fieldFor(detail: string): string {\n"
            '  return detail === "Account name already exists" ? "name" : "form";\n'
            "}\n"
        ),
    }

    assert report_from(tmp_path, files) == [
        (
            'web/account.ts:2: branches on human-readable error text "Account '
            'name already exists" produced at server/account.py:2; use a '
            "stable error code and handler registry"
        )
    ]


def test_allows_stable_machine_error_codes(tmp_path: Path) -> None:
    files = {
        "server/account.py": (
            "def register():\n"
            "    return JsonResponse(content='account_name_exists')\n"
        ),
        "web/account.ts": (
            "export function fieldFor(code: string): string {\n"
            '  return code === "account_name_exists" ? "name" : "form";\n'
            "}\n"
        ),
    }

    assert report_from(tmp_path, files) == []


def test_allows_human_message_used_only_for_display(tmp_path: Path) -> None:
    files = {
        "server/account.py": (
            "def register():\n"
            "    return JsonResponse(content='Account name already exists')\n"
        ),
        "web/account.ts": (
            'export const shown = { message: "Account name already exists" };\n'
        ),
    }

    assert report_from(tmp_path, files) == []


def test_flags_typescript_error_text_compared_in_python(
    tmp_path: Path,
) -> None:
    files = {
        "web/error.ts": (
            'export const failure = { error: "Remote service did not answer" };\n'
        ),
        "worker/retry.py": (
            "def should_retry(reason):\n"
            "    return reason == 'Remote service did not answer'\n"
        ),
    }

    assert report_from(tmp_path, files) == [
        (
            'worker/retry.py:2: branches on human-readable error text "Remote '
            'service did not answer" produced at web/error.ts:1; use a stable '
            "error code and handler registry"
        )
    ]
