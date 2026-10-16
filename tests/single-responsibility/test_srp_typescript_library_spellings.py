"""
A catalogued TypeScript library reaches its entity through each of its
documented spellings, and content hashing is never authentication, as the
Python twin pins (hashlib in NON_ENTITY_SOURCES). Domain: one sync unit
that writes a file and uses one library spelling. Oracle: the catalogue
contract - the unit reaches filesystem plus the library's entity.

Concrete inputs -> expected outputs:
- input:
      import * as fs from "node:fs";
      import fetch from "node-fetch";
      export async function sync(path: string) {
        await fetch(path); fs.writeFileSync(path, "x"); }
  output: expected ["filesystem", "network"], got ["filesystem"] - calling
  the default export of node-fetch, axios or got is their request.
- input: `import * as https from "https"; https.get(path)`
  output: expected ["filesystem", "network"], got ["filesystem"] - only
  the node:https spelling was catalogued.
- input: `import { Queue } from "bullmq"; await new Queue("mail").add(...)`
  output: expected ["filesystem", "queue"], got ["filesystem"].
- input: `import mysql from "mysql2/promise"; ... connection.query(...)`
  output: expected ["filesystem", "persistence"], got ["filesystem"].
- input: `createHash("sha256").update(fs.readFileSync(path)).digest("hex")`
  output: expected ["filesystem"], got ["authentication", "filesystem"].
"""

from pathlib import Path

import pytest
from srp_support import run_report, unit_named

SPELLINGS = {
    "node_fetch_default": (
        'import fetch from "node-fetch";',
        "await fetch(path);",
        ["filesystem", "network"],
    ),
    "axios_default": (
        'import axios from "axios";',
        "await axios({ url: path });",
        ["filesystem", "network"],
    ),
    "got_default": (
        'import got from "got";',
        "await got(path);",
        ["filesystem", "network"],
    ),
    "https_bare": (
        'import * as https from "https";',
        "https.get(path);",
        ["filesystem", "network"],
    ),
    "http_bare_default": (
        'import http from "http";',
        "http.request(path);",
        ["filesystem", "network"],
    ),
    "net_bare": (
        'import * as net from "net";',
        "net.connect(80);",
        ["filesystem", "network"],
    ),
    "bullmq_add": (
        'import { Queue } from "bullmq";',
        'await new Queue("mail").add("send", { path });',
        ["filesystem", "queue"],
    ),
    "mysql2_promise": (
        'import mysql from "mysql2/promise";',
        (
            "const connection = await mysql.createConnection({});\n"
            '  await connection.query("select 1");'
        ),
        ["filesystem", "persistence"],
    ),
    "content_hash": (
        'import { createHash } from "node:crypto";',
        'createHash("sha256").update(fs.readFileSync(path)).digest("hex");',
        ["filesystem"],
    ),
}


@pytest.mark.parametrize("spelling", sorted(SPELLINGS))
def test_library_spelling_reaches_its_catalogued_entity(
    tmp_path: Path, spelling: str
) -> None:
    import_line, call, entities = SPELLINGS[spelling]
    source = (
        f'import * as fs from "node:fs";\n{import_line}\n'
        "export async function sync(path: string) {\n"
        f'  {call}\n  fs.writeFileSync(path, "x");\n}}\n'
    )

    report = run_report(tmp_path, source, ".ts")

    assert unit_named(report, "<module>.sync")["entities"] == entities
