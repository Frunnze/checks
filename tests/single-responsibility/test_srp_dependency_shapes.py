import pytest
from srp_support import run_project, run_report, unit_named, write_split_project


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_module_type_alias_declarations_resolve_dependency_operations(tmp_path, suffix):
    source = (
        "from httpx import Client\ntype Remote = Client\n"
        "def work(client: Remote):\n    client.get('url')\n"
        if suffix == ".py"
        else 'import type {AxiosInstance} from "axios";\ntype Remote = AxiosInstance;\n'
        "function work(client: Remote) { client.get('url'); }\n"
    )
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.work")

    assert "network" in unit["effect_domains"]
    assert unit["metrics"]["statements"] == 1


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_clients_using_constructor_injection_still_corroborate_separate_groups(
    tmp_path, suffix
):
    write_split_project(tmp_path, suffix)
    for group, first in enumerate((0, 2)):
        for index in range(2):
            source = (
                "from worker import Worker\nclass Client:\n"
                "    def __init__(self, worker: Worker):\n        self.worker = worker\n"
                f"    def use(self):\n        self.worker.task_{first}()\n        self.worker.task_{first + 1}()\n"
                if suffix == ".py"
                else 'import {Worker} from "./worker";\nclass Client {\n'
                "constructor(private worker: Worker) {}\n"
                f"use() {{ this.worker.task_{first}(); this.worker.task_{first + 1}(); }}\n}}\n"
            )
            (tmp_path / f"client_{group}_{index}{suffix}").write_text(source)

    assert unit_named(run_project(tmp_path), "<module>.Worker")["coefficient"] == 0.5


def test_default_arrow_wrappers_propagate_external_clients(tmp_path):
    write_split_project(tmp_path, ".ts")
    for group in range(2):
        source = (tmp_path / f"client_{group}_0.ts").read_text()
        (tmp_path / f"wrapper_{group}.ts").write_text(
            source.replace("function use()", "export default () =>")
        )
        for index in range(2):
            (tmp_path / f"client_{group}_{index}.ts").write_text(
                f'import run from "./wrapper_{group}";\nrun();\n'
            )

    assert unit_named(run_project(tmp_path), "<module>.Worker")["coefficient"] == 0.5


def test_reexported_local_fetch_is_not_the_browser_builtin(tmp_path):
    (tmp_path / "local.ts").write_text(
        "function fetch(value) { return value; }\nexport {fetch};\n"
    )
    (tmp_path / "client.ts").write_text(
        'import {fetch} from "./local";\nfunction work() { fetch("url"); }\n'
    )
    unit = unit_named(run_project(tmp_path), "<module>.work")

    assert unit["effect_domains"] == {}
