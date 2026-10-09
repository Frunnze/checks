import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from srp_support import CHECK, split_class

WORKER_CLASS_NAME = "<module>.Worker"
WORKER_ENTITIES = ["filesystem", "network"]
WORKER_REASON = "Synthetic reviewed adapter with one reason to change."
UTF8_BYTE_ORDER_MARK = "﻿"


def reviewed_worker_source() -> str:
    return split_class().replace(
        "return value", "result = str(value)\n        return result"
    )


def worker_whitelist_entry(
    path: str = "worker.py", **changes: Any
) -> dict[str, Any]:
    return {
        "path": path,
        "kind": "class",
        "name": WORKER_CLASS_NAME,
        "entities": WORKER_ENTITIES,
        "reason": WORKER_REASON,
        **changes,
    }


def whitelist_text(entries: list[dict[str, Any]]) -> str:
    lines = [json.dumps(entry) for entry in entries]
    return "\n".join(lines) + "\n"


def scan_with_whitelist(
    root: Path, whitelist_contents: str, targets: list[Path]
) -> subprocess.CompletedProcess[str]:
    whitelist = root / "whitelist.txt"
    whitelist.write_text(whitelist_contents, encoding="utf-8")
    command = [
        sys.executable,
        str(CHECK / "srp_check.py"),
        "--json",
        "--whitelist",
        str(whitelist),
    ]
    command.extend(str(target) for target in targets)
    return subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
