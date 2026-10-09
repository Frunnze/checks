import json
import subprocess
import sys
from pathlib import Path

from check_support import TOOLKIT

CHECK = TOOLKIT / "checks" / "experimental" / "single-responsibility" / "python"
sys.path.insert(0, str(CHECK))

from python_facts import python_facts
from srp_check import analyze, report_for
from srp_cohesion import entity_members, members_of, owner_score
from srp_effects import effect_domains
from srp_entities import external_entities, reason_coefficient
from srp_metrics import (
    THRESHOLD,
    CallableFacts,
    callable_score,
    entity_reasons,
)

__all__ = [
    "CHECK",
    "THRESHOLD",
    "CallableFacts",
    "analyze",
    "callable_score",
    "effect_domains",
    "entity_members",
    "entity_reasons",
    "external_entities",
    "members_of",
    "mixed_function",
    "owner_score",
    "python_facts",
    "reason_coefficient",
    "report_for",
    "run_project",
    "run_report",
    "split_class",
    "unit_named",
    "write_split_project",
]


def run_report(tmp_path: Path, source: str, suffix: str = ".py") -> dict:
    path = tmp_path / f"source with spaces{suffix}"
    path.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CHECK / "srp_check.py"), "--json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    report = json.loads(result.stdout)
    assert result.returncode == int(report["failed"])
    return report


def run_project(root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(CHECK / "srp_check.py"), "--json", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    return json.loads(result.stdout)


def write_split_project(root: Path, suffix: str, source: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    source = split_class(suffix) if source is None else source
    if suffix != ".py":
        source = source.replace("class Worker", "export class Worker")
    (root / ("worker" + suffix)).write_text(source)
    for group, task in enumerate((0, 2)):
        for client in range(2):
            if suffix == ".py":
                body = (
                    "from worker import Worker\ndef use():\n    worker = Worker()\n"
                    f"    worker.task_{task}()\n    worker.task_{task + 1}()\n"
                )
            else:
                body = (
                    'import {Worker} from "./worker";\nfunction use() {\n'
                    "  const worker = new Worker();\n"
                    f"  worker.task_{task}();\n  worker.task_{task + 1}();\n}}\n"
                )
            (root / f"client_{group}_{client}{suffix}").write_text(body)


def unit_named(report: dict, name: str) -> dict:
    return next(
        unit
        for file in report["files"]
        for unit in file["units"]
        if unit["name"] == name
    )


def split_class(suffix: str = ".py", cohesive: bool = False) -> str:
    if suffix == ".py":
        source = "import httpx\nfrom pathlib import Path\n\n\nclass Worker:\n"
        for i in range(4):
            body = (
                "        return httpx.get(name).text\n"
                if cohesive or i < 2
                else "        return Path(name).read_text()\n"
            )
            source += f"    def task_{i}(self, name):\n" + body
        return source
    source = (
        'import axios from "axios";\nimport * as fs from "node:fs";\n\nclass Worker {\n'
    )
    for i in range(4):
        body = (
            "    return axios.get(name);\n"
            if cohesive or i < 2
            else "    return fs.readFileSync(name);\n"
        )
        source += f"  task_{i}(name) {{\n" + body + "  }\n"
    return source + "}\n"


def mixed_function(suffix: str = ".py", mixed: bool = True) -> str:
    if suffix == ".py":
        source = "import httpx\nfrom pathlib import Path\ndef work():\n"
        for i in range(70):
            source += f"    value_{i} = {i}\n"
        for i in range(12):
            source += f"    if value_{i}:\n        value_{i} += 1\n"
        source += (
            "    address = str(" + " + ".join(f"value_{i}" for i in range(35)) + ")\n"
        )
        source += "    httpx.get(address)\n    httpx.post(address)\n"
        if mixed:
            source += (
                "    filename = str("
                + " + ".join(f"value_{i}" for i in range(35, 70))
                + ")\n"
            )
            source += (
                "    Path(filename).read_text()\n    Path(filename).write_text('x')\n"
            )
        return source
    source = 'import * as fs from "node:fs";\nimport axios from "axios";\n'
    source += "async function work() {\n"
    for i in range(70):
        source += f"  let value_{i} = {i};\n"
    for i in range(12):
        source += f"  if (value_{i}) {{ value_{i} += 1; }}\n"
    source += (
        "  const address = String("
        + " + ".join(f"value_{i}" for i in range(35))
        + ");\n"
    )
    source += "  axios.get(address);\n  axios.post(address);\n"
    if mixed:
        source += (
            "  const filename = String("
            + " + ".join(f"value_{i}" for i in range(35, 70))
            + ");\n"
        )
        source += '  fs.readFileSync(filename);\n  fs.writeFileSync(filename, "x");\n'
    return source + "}\n"
