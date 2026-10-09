import pytest
from srp_support import (
    THRESHOLD,
    run_project,
    run_report,
    unit_named,
    write_split_project,
)
from test_srp_delegation import delegated_source, helper_source


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_class_methods_can_call_module_helpers(tmp_path, suffix):
    work = delegated_source(suffix)
    if suffix == ".py":
        work = "class Worker:\n" + "\n".join(
            "    " + line for line in work.replace("work()", "work(self)").splitlines()
        )
    else:
        work = (
            "class Worker {\n"
            + work.replace("async function work", "async work")
            + "}\n"
        )
    unit = unit_named(
        run_report(tmp_path, helper_source(suffix) + work, suffix),
        "<module>.Worker.work",
    )

    assert unit["coefficient"] >= THRESHOLD
    assert set(unit["delegated_effect_domains"]) == {"network", "filesystem"}


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_nested_helpers_are_resolved_in_their_enclosing_scope(tmp_path, suffix):
    helpers = helper_source(suffix).replace("export function", "function")
    source = delegated_source(suffix)
    if suffix == ".py":
        # Imports remain at module scope, helper definitions move into work.
        imports, helpers = helpers.split("def transfer", 1)
        helpers = "def transfer" + helpers
        nested = "\n".join("    " + line for line in helpers.splitlines()) + "\n"
        source = imports + source.replace("def work():\n", "def work():\n" + nested)
    else:
        imports, helpers = helpers.split("function transfer", 1)
        source = imports + source.replace(
            "work() {\n", "work() {\nfunction transfer" + helpers
        )
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.work")

    assert unit["coefficient"] >= THRESHOLD
    assert set(unit["metrics"]["links"]) == {
        "<module>.work.transfer",
        "<module>.work.store",
    }


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_member_helper_effects_reach_the_calling_method(tmp_path, suffix):
    if suffix == ".py":
        source = (
            "import httpx\nfrom pathlib import Path\nclass Worker:\n"
            "    def load(self, address):\n        self.response = httpx.get(address)\n"
            "        httpx.post(address)\n"
            "    def save(self, filename):\n        Path(filename).read_text()\n"
            "        Path(filename).write_text(self.response.text)\n"
        )
        work = delegated_source(suffix).replace("work()", "work(self)")
        work = work.replace("transfer(address)", "self.load(address)").replace(
            "store(filename, 'x')", "self.save(filename)"
        )
        source += "\n".join("    " + line for line in work.splitlines()) + "\n"
    else:
        source = (
            'import axios from "axios";\nimport * as fs from "node:fs";\nclass Worker {\n'
            "load(address) { this.response = axios.get(address); axios.post(address); }\n"
            "save(filename) { fs.readFileSync(filename); fs.writeFileSync(filename, this.response); }\n"
        )
        work = delegated_source(suffix).replace("async function work", "async work")
        work = work.replace("transfer(address)", "this.load(address)").replace(
            'store(filename, "x")', "this.save(filename)"
        )
        source += work + "}\n"
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.Worker.work")

    assert set(unit["effect_domains"]) == {"network", "filesystem"}
    assert unit["coefficient"] >= THRESHOLD


@pytest.mark.parametrize("suffix", [".py", ".ts"])
@pytest.mark.parametrize("shared_client", [False, True])
def test_separate_effect_groups_survive_a_shared_helper_module(
    tmp_path, suffix, shared_client
):
    (tmp_path / ("helpers" + suffix)).write_text(helper_source(suffix))
    if suffix == ".py":
        source = "import helpers\nclass Worker:\n"
        for index in range(4):
            call = "transfer(value)" if index < 2 else "store(value, 'x')"
            source += (
                f"    def task_{index}(self):\n        value = str(self.entity)\n"
                + "        value += 'x'\n" * 4
                + f"        return helpers.{call}\n"
            )
    else:
        source = 'import * as helpers from "./helpers";\nclass Worker {\n'
        for index in range(4):
            call = "transfer(value)" if index < 2 else 'store(value, "x")'
            source += (
                f"task_{index}() {{\nlet value = String(this.entity);\n"
                + 'value += "x";\n' * 4
                + f"return helpers.{call};\n}}\n"
            )
        source += "}\n"
    write_split_project(tmp_path, suffix, source)
    if shared_client:
        (tmp_path / ("shared" + suffix)).write_text(
            (tmp_path / ("client_0_0" + suffix)).read_text()
            + (tmp_path / ("client_1_0" + suffix)).read_text().replace("use", "another")
        )
    owner = unit_named(run_project(tmp_path), "<module>.Worker")

    assert owner["entities"] == ["filesystem", "network"]
    assert owner["coefficient"] >= THRESHOLD


@pytest.mark.parametrize("suffix", [".py", ".ts"])
@pytest.mark.parametrize("imported", [False, True])
def test_reassigned_helpers_are_not_resolved_by_their_original_names(
    tmp_path, suffix, imported
):
    source = helper_source(suffix)
    source += (
        "transfer = lambda value: value\nstore = lambda name, data: data\n"
        if suffix == ".py"
        else "transfer = value => value;\nstore = (name, data) => data;\n"
    )
    if imported:
        (tmp_path / ("helpers" + suffix)).write_text(source)
        imports = (
            "from helpers import transfer, store\n"
            if suffix == ".py"
            else 'import {transfer, store} from "./helpers";\n'
        )
        (tmp_path / ("worker" + suffix)).write_text(imports + delegated_source(suffix))
        report = run_project(tmp_path)
    else:
        report = run_report(tmp_path, source + delegated_source(suffix), suffix)
    unit = unit_named(report, "<module>.work")

    assert unit["effect_domains"] == {}


@pytest.mark.parametrize("suffix", [".py", ".ts"])
@pytest.mark.parametrize("shadowed", [False, True])
def test_local_aliases_follow_the_resolved_binding(tmp_path, suffix, shadowed):
    source = delegated_source(suffix).replace("transfer(address)", "send(address)")
    if suffix == ".py":
        source = source.replace("def work():\n", "def work():\n    send = transfer\n")
    else:
        source = source.replace("work() {\n", "work() {\n  const send = transfer;\n")
    if shadowed:
        source = source.replace("work()", "work(transfer)")
    unit = unit_named(
        run_report(tmp_path, helper_source(suffix) + source, suffix), "<module>.work"
    )

    assert ("network" in unit["effect_domains"]) is not shadowed
    assert (unit["coefficient"] >= THRESHOLD) is not shadowed


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_wrappers_do_not_multiply_distinct_operation_evidence(tmp_path, suffix):
    helpers = helper_source(suffix).replace(".post(address)", ".get(address)")
    unit = unit_named(
        run_report(tmp_path, helpers + delegated_source(suffix), suffix),
        "<module>.work",
    )

    assert len(unit["effect_domains"]["network"]) == 1
    assert unit["entities"] == ["filesystem", "network"]


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_replaced_instance_method_does_not_use_its_old_body(tmp_path, suffix):
    source = (
        "import httpx\nclass Worker:\n"
        "    def send(self):\n        httpx.get('a')\n        httpx.post('a')\n"
        "    def work(self, callback):\n        self.send = callback\n        self.send()\n"
        if suffix == ".py"
        else 'import axios from "axios";\nclass Worker {\n'
        'send() { axios.get("a"); axios.post("a"); }\n'
        "work(callback) { this.send = callback; this.send(); }\n}\n"
    )
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.Worker.work")

    assert unit["effect_domains"] == {}
    assert unit["metrics"]["links"] == []
