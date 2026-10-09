import json
import subprocess
import sys

import pytest
from srp_support import CHECK, run_project, unit_named, write_split_project


@pytest.mark.parametrize("package", [True, False])
def test_python_flat_packages_and_namespaces_without_src(tmp_path, package):
    write_split_project(tmp_path, ".py")
    domain = tmp_path / "domain"
    domain.mkdir()
    (tmp_path / "worker.py").rename(domain / "worker.py")
    if package:
        (domain / "__init__.py").write_text("")
    for client in tmp_path.glob("client*"):
        client.write_text(
            client.read_text().replace(
                "from worker import", "from domain.worker import"
            )
        )

    assert unit_named(run_project(tmp_path), "<module>.Worker")["coefficient"] == 0.5


def test_python_reexported_class_aliases_preserve_clients(tmp_path):
    write_split_project(tmp_path, ".py")
    package = tmp_path / "package"
    package.mkdir()
    (tmp_path / "worker.py").rename(package / "worker.py")
    (package / "__init__.py").write_text("from .worker import Worker as Public\n")
    for client in tmp_path.glob("client*"):
        client.write_text(
            client.read_text().replace(
                "from worker import Worker", "from package import Public as Worker"
            )
        )

    assert unit_named(run_project(tmp_path), "<module>.Worker")["coefficient"] == 0.5


def test_explicit_root_resolves_individually_selected_namespace_files(tmp_path):
    root = tmp_path / "code"
    write_split_project(root, ".py")
    domain = root / "domain"
    domain.mkdir()
    for file in list(root.glob("*.py")):
        file.write_text(
            file.read_text().replace("from worker import", "from domain.worker import")
        )
        file.rename(domain / file.name)
    result = subprocess.run(
        [
            sys.executable,
            str(CHECK / "srp_check.py"),
            "--json",
            "--source-root",
            str(root),
        ]
        + [str(path) for path in sorted(domain.glob("*.py"))],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    assert {file["source_root"] for file in json.loads(result.stdout)["files"]} == {
        str(root)
    }


@pytest.mark.parametrize("suffix", [".ts", ".tsx", ".mts", ".cts"])
def test_typescript_modules_resolve_across_folders_and_module_extensions(
    tmp_path, suffix
):
    write_split_project(tmp_path, suffix)
    (tmp_path / "domain").mkdir()
    (tmp_path / "clients").mkdir()
    (tmp_path / ("worker" + suffix)).rename(tmp_path / "domain" / ("worker" + suffix))
    extension = {".mts": ".mjs", ".cts": ".cjs"}.get(suffix, ".js")
    for client in tmp_path.glob("client_*" + suffix):
        client.write_text(
            client.read_text().replace("./worker", "../domain/worker" + extension)
        )
        client.rename(tmp_path / "clients" / client.name)

    assert unit_named(run_project(tmp_path), "<module>.Worker")["coefficient"] == 0.5


@pytest.mark.parametrize("form", ["default", "renamed", "star", "forward_default"])
def test_typescript_export_forms_are_resolved(tmp_path, form):
    write_split_project(tmp_path, ".ts")
    worker = tmp_path / "worker.ts"
    if form in {"default", "forward_default"}:
        worker.write_text(
            worker.read_text().replace(
                "export class Worker", "export default class Worker"
            )
        )
    bridge = {
        "default": 'export {default} from "./worker";',
        "renamed": 'export {Worker as Public} from "./worker";',
        "star": 'export * from "./worker";',
        "forward_default": 'export {default as Worker} from "./worker";',
    }[form]
    (tmp_path / "public.ts").write_text(bridge)
    for client in tmp_path.glob("client*.ts"):
        source = client.read_text().replace("./worker", "./public")
        if form == "default":
            source = source.replace("{Worker}", "Worker")
        elif form == "renamed":
            source = source.replace("{Worker}", "{Public as Worker}")
        client.write_text(source)

    assert unit_named(run_project(tmp_path), "<module>.Worker")["coefficient"] == 0.5


def test_typescript_paths_respect_inherited_tsconfig(tmp_path):
    write_split_project(tmp_path, ".ts")
    (tmp_path / "domain").mkdir()
    (tmp_path / "worker.ts").rename(tmp_path / "domain/worker.ts")
    (tmp_path / "base.json").write_text(
        json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"@domain/*": ["domain/*"]}}}
        )
    )
    (tmp_path / "tsconfig.json").write_text('{"extends":"./base.json"}')
    for client in tmp_path.glob("client*.ts"):
        client.write_text(client.read_text().replace("./worker", "@domain/worker"))
    report = run_project(tmp_path)

    assert unit_named(report, "<module>.Worker")["coefficient"] == 0.5
    assert report["typescript_configs"] == [str(tmp_path / "tsconfig.json")]


def test_ambiguous_reexports_and_cycles_terminate_without_inventing_entities(tmp_path):
    write_split_project(tmp_path, ".ts")
    (tmp_path / "other.ts").write_text((tmp_path / "worker.ts").read_text())
    (tmp_path / "public.ts").write_text(
        'export * from "./worker"; export * from "./other"; export * from "./loop";'
    )
    (tmp_path / "loop.ts").write_text('export * from "./public";')
    for client in tmp_path.glob("client*.ts"):
        client.write_text(client.read_text().replace("./worker", "./public"))

    assert unit_named(run_project(tmp_path), "<module>.Worker")["entities"] == [
        "filesystem",
        "network",
    ]
