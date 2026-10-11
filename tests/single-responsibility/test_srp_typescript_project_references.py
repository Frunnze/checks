import json

from srp_support import run_project, unit_named

ALIASED_HELPERS = {
    "src/load.ts": (
        'import axios from "axios";\n'
        "export function load(path: string) { return axios.get(path); }\n"
    ),
    "src/read.ts": (
        'import * as fs from "node:fs";\n'
        "export function read(path: string) { return fs.readFileSync(path); }\n"
    ),
    "src/work.ts": (
        'import { load } from "@/load";\n'
        'import { read } from "@/read";\n'
        "export function work(path: string) {\n"
        "  load(path);\n"
        "  read(path);\n"
        "}\n"
    ),
}
SOLUTION_TSCONFIGS = {
    "tsconfig.json": {
        "files": [],
        "references": [
            {"path": "./tsconfig.app.json"},
            {"path": "./tsconfig.node.json"},
        ],
    },
    "tsconfig.app.json": {
        "compilerOptions": {"paths": {"@/*": ["./src/*"]}},
        "include": ["src"],
    },
    "tsconfig.node.json": {"include": ["vite.config.ts"]},
}


def test_solution_tsconfig_resolves_aliases_of_the_referenced_project(
    tmp_path,
):
    (tmp_path / "src").mkdir()
    for relative, source in ALIASED_HELPERS.items():
        (tmp_path / relative).write_text(source)
    for name, config in SOLUTION_TSCONFIGS.items():
        (tmp_path / name).write_text(json.dumps(config))

    report = run_project(tmp_path)

    work = unit_named(report, "<module>.work")
    assert work["entities"] == ["filesystem", "network"]
    assert report["typescript_configs"] == [
        str(tmp_path / "tsconfig.app.json")
    ]
