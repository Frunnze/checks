import pytest
from srp_support import THRESHOLD, mixed_function, run_project, run_report, unit_named


def helper_source(suffix):
    if suffix == ".py":
        return (
            "import httpx\nfrom pathlib import Path\n"
            "def transfer(address):\n    httpx.get(address)\n    return httpx.post(address)\n"
            "def store(filename, data):\n    Path(filename).read_text()\n"
            "    Path(filename).write_text(data)\n"
        )
    return (
        'import axios from "axios";\nimport * as fs from "node:fs";\n'
        "export function transfer(address) {\n  axios.get(address);\n"
        "  return axios.post(address);\n}\n"
        "export function store(filename, data) {\n  fs.readFileSync(filename);\n"
        "  fs.writeFileSync(filename, data);\n}\n"
    )


def delegated_source(suffix, chained=False):
    source = mixed_function(suffix)
    if suffix == ".py":
        source = source.replace("import httpx\nfrom pathlib import Path\n", "")
        source = source.replace(
            "httpx.get(address)\n    httpx.post(address)",
            "response = transfer(address)" if chained else "transfer(address)",
        )
        return source.replace(
            "Path(filename).read_text()\n    Path(filename).write_text('x')",
            "store(filename, response)" if chained else "store(filename, 'x')",
        )
    source = source.replace(
        'import * as fs from "node:fs";\nimport axios from "axios";\n', ""
    )
    source = source.replace(
        "axios.get(address);\n  axios.post(address)",
        "const response = await transfer(address)" if chained else "transfer(address)",
    )
    return source.replace(
        'fs.readFileSync(filename);\n  fs.writeFileSync(filename, "x")',
        "store(filename, response)" if chained else 'store(filename, "x")',
    )


@pytest.mark.parametrize("suffix", [".py", ".ts", ".tsx"])
@pytest.mark.parametrize("chained", [False, True])
def test_local_helpers_preserve_entities(tmp_path, suffix, chained):
    source = helper_source(suffix) + delegated_source(suffix, chained)
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.work")

    assert unit["coefficient"] >= THRESHOLD
    assert unit["entities"] == ["filesystem", "network"]
    assert unit["direct_effect_domains"] == {}
    assert set(unit["delegated_effect_domains"]) == {"network", "filesystem"}
    assert all("via resolved helpers" in reason for reason in unit["reasons"][:2])


@pytest.mark.parametrize("suffix", [".py", ".ts"])
@pytest.mark.parametrize("chained", [False, True])
def test_imported_helpers_and_reexports_preserve_effects(tmp_path, suffix, chained):
    (tmp_path / ("helpers" + suffix)).write_text(helper_source(suffix))
    (tmp_path / ("bridge" + suffix)).write_text(
        "from helpers import transfer, store\n"
        if suffix == ".py"
        else 'export {transfer, store} from "./helpers";\n'
    )
    imports = (
        "from bridge import transfer, store\n"
        if suffix == ".py"
        else 'import {transfer, store} from "./bridge";\n'
    )
    (tmp_path / ("worker" + suffix)).write_text(
        imports + delegated_source(suffix, chained)
    )
    unit = unit_named(run_project(tmp_path), "<module>.work")

    assert unit["coefficient"] >= THRESHOLD
    targets = [
        target for block in unit["metrics"]["flow"] for target in block["callees"]
    ]
    assert {target["name"] for target in targets} == {
        "<module>.transfer",
        "<module>.store",
    }
    assert {target["path"] for target in targets} == {
        str(tmp_path / ("helpers" + suffix))
    }


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_a_coordinator_inherits_helper_entities_but_not_their_size(tmp_path, suffix):
    if suffix == ".py":
        source = mixed_function().replace("def work():", "def implementation():")
        source += "def coordinate():\n    return implementation()\n"
    else:
        source = mixed_function(suffix).replace(
            "function work()", "function implementation()"
        )
        source += "function coordinate() { return implementation(); }\n"
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.coordinate")

    assert unit["coefficient"] >= THRESHOLD
    assert unit["metrics"]["statements"] == 1
    assert unit["metrics"]["complexity"] == 1
    assert set(unit["delegated_effect_domains"]) == {"network", "filesystem"}


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_referenced_but_uncalled_helper_does_not_add_effects(tmp_path, suffix):
    (tmp_path / ("helpers" + suffix)).write_text(helper_source(suffix))
    source = delegated_source(suffix)
    if suffix == ".py":
        source = "from helpers import transfer, store\n" + source.replace(
            "transfer(address)", "callback = transfer"
        ).replace("store(filename, 'x')", "callback = store")
    else:
        source = 'import {transfer, store} from "./helpers";\n' + source.replace(
            "transfer(address)", "const callback = transfer"
        ).replace('store(filename, "x")', "const another = store")
    (tmp_path / ("worker" + suffix)).write_text(source)
    unit = unit_named(run_project(tmp_path), "<module>.work")

    assert unit["effect_domains"] == {}
    assert unit["metrics"]["delegated_effects"] == []


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_transitive_and_recursive_helpers_reach_a_stable_summary(tmp_path, suffix):
    source = helper_source(suffix).replace("transfer(address)", "send(address)")
    if suffix == ".py":
        source += (
            "def transfer(address):\n    return relay(address)\n"
            "def relay(address):\n    if not address:\n        return transfer(address)\n"
            "    return send(address)\n"
        )
    else:
        source += (
            "function transfer(address) { return relay(address); }\n"
            "function relay(address) {\n  if (!address) return transfer(address);\n"
            "  return send(address);\n}\n"
        )
    unit = unit_named(
        run_report(tmp_path, source + delegated_source(suffix), suffix), "<module>.work"
    )

    assert unit["coefficient"] >= THRESHOLD
    assert len(unit["delegated_effect_domains"]["network"]) == 2


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_shadowed_local_helper_is_not_followed(tmp_path, suffix):
    source = helper_source(suffix) + delegated_source(suffix).replace(
        "work()", "work(transfer, store)"
    )
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.work")

    assert unit["effect_domains"] == {}
    assert unit["coefficient"] < THRESHOLD


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_duplicate_definitions_abstain_from_summarizing(tmp_path, suffix):
    source = helper_source(suffix)
    source += (
        "def transfer(address):\n    return address\ndef store(filename, data):\n    return data\n"
        if suffix == ".py"
        else "function transfer(address) { return address; }\nfunction store(filename, data) { return data; }\n"
    )
    unit = unit_named(
        run_report(tmp_path, source + delegated_source(suffix), suffix), "<module>.work"
    )

    assert unit["effect_domains"] == {}
