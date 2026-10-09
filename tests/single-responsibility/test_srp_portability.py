import json
import shutil
import subprocess
import sys

import pytest
from srp_support import (
    CHECK,
    THRESHOLD,
    mixed_function,
    run_project,
    unit_named,
    write_split_project,
)


@pytest.mark.parametrize(
    "form",
    ["require_namespace", "require_destructure", "import_equals", "export_equals"],
)
def test_typescript_static_commonjs_import_forms(tmp_path, form):
    write_split_project(tmp_path, ".ts")
    if form == "export_equals":
        worker = tmp_path / "worker.ts"
        worker.write_text(
            worker.read_text().replace("export class", "class") + "export = Worker;\n"
        )
    for client in tmp_path.glob("client*.ts"):
        source = client.read_text()
        replacement = {
            "require_namespace": 'const module = require("./worker");',
            "require_destructure": 'const {Worker} = require("./worker");',
            "import_equals": 'import module = require("./worker");',
            "export_equals": 'import Worker = require("./worker");',
        }[form]
        source = source.replace('import {Worker} from "./worker";', replacement)
        if form in {"require_namespace", "import_equals"}:
            source = source.replace("new Worker()", "new module.Worker()")
        client.write_text(source)

    assert unit_named(run_project(tmp_path), "<module>.Worker")["coefficient"] == 0.5


@pytest.mark.parametrize("suffix", [".py", ".ts"])
@pytest.mark.parametrize("workflow", [False, True])
def test_imported_dependency_type_aliases_keep_entities_visible(
    tmp_path, suffix, workflow
):
    source = mixed_function(suffix)
    if suffix == ".py":
        (tmp_path / "dependencies.py").write_text(
            "from typing import Annotated\nfrom httpx import Client\n"
            "Remote = Annotated[Client, unexecuted_metadata()]\n"
        )
        source = "from dependencies import Remote\n" + source.replace(
            "def work():", "def work(client: Remote):"
        )
        source = source.replace("httpx.get(", "client.get(").replace(
            "httpx.post(", "client.post("
        )
        if workflow:
            source = source.replace(
                "    client.get(address)", "    response = client.get(address)"
            ).replace("write_text('x')", "write_text(response.text)")
    else:
        (tmp_path / "dependencies.ts").write_text(
            'import type {AxiosInstance} from "axios";\nexport type Remote = AxiosInstance;\n'
        )
        source = 'import type {Remote} from "./dependencies";\n' + source.replace(
            "work()", "work(client: Remote)"
        )
        source = source.replace("axios.get(", "client.get(").replace(
            "axios.post(", "client.post("
        )
        if workflow:
            source = source.replace(
                "  client.get(address)", "  const response = await client.get(address)"
            ).replace(
                'writeFileSync(filename, "x")', "writeFileSync(filename, response.data)"
            )
    (tmp_path / ("worker" + suffix)).write_text(source)
    unit = unit_named(run_project(tmp_path), "<module>.work")

    assert unit["coefficient"] >= THRESHOLD
    assert set(unit["effect_domains"]) == {"network", "filesystem"}
    assert unit["metrics"]["call_aliases"]


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_project_modules_named_like_libraries_are_not_assumed_to_be_those_libraries(
    tmp_path, suffix
):
    (tmp_path / ("worker" + suffix)).write_text(mixed_function(suffix))
    if suffix == ".py":
        (tmp_path / "httpx.py").write_text(
            "def get(value):\n    return value\ndef post(value):\n    return value\n"
        )
    else:
        (tmp_path / "local.ts").write_text(
            "export default class Local { get(value) { return value; } post(value) { return value; } }\n"
        )
        (tmp_path / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "baseUrl": ".",
                        "paths": {"axios": ["./local.ts"]},
                    }
                }
            )
        )
    unit = unit_named(run_project(tmp_path), "<module>.work")

    assert "network" not in unit["effect_domains"]
    assert unit["coefficient"] < THRESHOLD


def test_copied_checker_works_outside_this_repository(tmp_path):
    tool = tmp_path / "tools" / "architecture"
    shutil.copytree(
        CHECK.parent, tool, ignore=shutil.ignore_patterns("__pycache__")
    )
    project = tmp_path / "unrelated-project"
    write_split_project(project, ".ts")
    (project / "node_modules").mkdir()
    (project / "node_modules/typescript").symlink_to(
        CHECK.parents[3] / "node_modules/typescript"
    )
    result = subprocess.run(
        [sys.executable, str(tool / "python" / "srp_check.py"), "--json", str(project)],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    assert (
        unit_named(json.loads(result.stdout), "<module>.Worker")["coefficient"] == 0.5
    )


@pytest.mark.parametrize("invalid", [False, True])
def test_explicit_tsconfig_and_config_errors_are_reported(tmp_path, invalid):
    write_split_project(tmp_path, ".ts")
    config = tmp_path / "build.json"
    config.write_text(
        '{"compilerOptions": {'
        if invalid
        else '{"compilerOptions": {"paths": {"@worker": ["./worker.ts"]}}}'
    )
    for client in tmp_path.glob("client*.ts"):
        client.write_text(client.read_text().replace("./worker", "@worker"))
    result = subprocess.run(
        [
            sys.executable,
            str(CHECK / "srp_check.py"),
            "--json",
            "--tsconfig",
            str(config),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == (2 if invalid else 1), result.stderr
    if invalid:
        assert not result.stdout
        assert str(config) in result.stderr
    else:
        assert json.loads(result.stdout)["typescript_configs"] == [str(config)]
