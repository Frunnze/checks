"""
Every finding the check prints can be whitelisted, even when two units of
one file share a name: TypeScript names each handler of an array of route
objects <module>.handler. A whitelist entry matches the whole finding, its
entities included, so same-named findings with different entities are
separate entries. Domain: a routes.ts with two handlers, each reaching two
of filesystem, network, persistence and process, the two pairs different.
Oracle: round trip - whitelisting every printed finding passes the gate.

Concrete inputs -> expected outputs:
- input (routes.ts):
      export const routes = [
        { path: "/0", handler: async (id: string) => {
            fs.writeFileSync(id, "x"); await db.query(id); } },
        { path: "/1", handler: async (id: string) => {
            await axios.get(id); await db.query(id); } },
      ];
  with a whitelist holding both printed <module>.handler findings,
  [filesystem, persistence] and [network, persistence]
  output: expected exit 0, got exit 2 "invalid SRP whitelist ...:
  duplicate finding" - the entries were keyed by path, kind and name only.
"""

import json
from pathlib import Path

from check_support import HYPOTHESIS_SETTINGS
from hypothesis import example, given
from hypothesis import strategies as st
from srp_whitelist_support import scan_with_whitelist, whitelist_text

EFFECTS = {
    "filesystem": 'fs.writeFileSync(id, "x")',
    "network": "await axios.get(id)",
    "persistence": "await db.query(id)",
    "process": "execSync(id)",
}
HEADER = (
    'import axios from "axios";\n'
    'import * as fs from "node:fs";\n'
    'import { Pool } from "pg";\n'
    'import { execSync } from "node:child_process";\n'
    "const db = new Pool();\n"
)
ENTITY_PAIRS = st.lists(
    st.sampled_from(sorted(EFFECTS)), min_size=2, max_size=2, unique=True
).map(sorted)


def _routes(handlers: list[list[str]]) -> str:
    rows = ""

    for index, entities in enumerate(handlers):
        body = " ".join(f"{EFFECTS[entity]};" for entity in entities)
        rows += (
            f'  {{ path: "/{index}", '
            f"handler: async (id: string) => {{ {body} }} }},\n"
        )

    return f"{HEADER}export const routes = [\n{rows}];\n"


def _printed_findings(report: dict) -> list[dict]:
    found = []

    for file in report["files"]:
        for unit in file["units"]:
            if unit["coefficient"] < report["threshold"]:
                continue

            found.append(
                {
                    "path": file["path"],
                    "kind": unit["kind"],
                    "name": unit["name"],
                    "entities": unit["entities"],
                    "reason": "Reviewed route handler.",
                }
            )

    return found


@given(
    first=ENTITY_PAIRS,
    second=ENTITY_PAIRS,
)
@example(
    first=["filesystem", "persistence"], second=["network", "persistence"]
)
@HYPOTHESIS_SETTINGS
def test_whitelist_property_accepts_every_printed_finding(
    tmp_path: Path, first: list[str], second: list[str]
) -> None:
    routes = tmp_path / "routes.ts"
    _ = routes.write_text(_routes([first, second]), encoding="utf-8")
    baseline = json.loads(scan_with_whitelist(tmp_path, "", [routes]).stdout)
    entries = _printed_findings(baseline)
    unique_entries = [
        json.loads(line)
        for line in sorted({json.dumps(entry) for entry in entries})
    ]

    finished = scan_with_whitelist(
        tmp_path, whitelist_text(unique_entries), [routes]
    )

    assert finished.returncode == 0, finished.stderr
