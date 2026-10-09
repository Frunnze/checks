import pytest
from srp_support import THRESHOLD, run_project, run_report, unit_named
from test_srp_delegation import delegated_source, helper_source


@pytest.mark.parametrize("scope", ["module", "nested", "class", "imported"])
@pytest.mark.parametrize("expression", ["arrow", "named"])
def test_typescript_function_values_keep_their_helper_identity(
    tmp_path, scope, expression
):
    helpers = helper_source(".ts")
    for name, arguments in [("transfer", "address"), ("store", "filename, data")]:
        value = (
            f"({arguments}) =>"
            if expression == "arrow"
            else f"function {name}_impl({arguments})"
        )
        helpers = helpers.replace(
            f"function {name}({arguments})", f"const {name} = {value}"
        )
    source = delegated_source(".ts")
    name = "<module>.work"
    if scope == "nested":
        imports, body = helpers.split("export const transfer", 1)
        body = "const transfer" + body.replace("export const", "const")
        source = imports + source.replace("work() {\n", "work() {\n" + body)
    elif scope == "class":
        name = "<module>.Worker.work"
        source = (
            helpers
            + "class Worker {\n"
            + source.replace("async function work", "async work")
            + "}\n"
        )
    elif scope == "imported":
        (tmp_path / "helpers.ts").write_text(helpers)
        (tmp_path / "worker.ts").write_text(
            'import {transfer, store} from "./helpers";\n' + source
        )
        unit = unit_named(run_project(tmp_path), name)
    else:
        source = helpers + source
    if scope != "imported":
        unit = unit_named(run_report(tmp_path, source, ".ts"), name)

    assert unit["coefficient"] >= THRESHOLD
    assert set(unit["effect_domains"]) == {"network", "filesystem"}


@pytest.mark.parametrize("nested", [False, True])
def test_reassigned_typescript_function_values_do_not_keep_stale_effects(
    tmp_path, nested
):
    helpers = helper_source(".ts").replace(
        "export function transfer(address)", "let transfer = function send(address)"
    )
    helpers = helpers.replace("export function store", "function store")
    source = delegated_source(".ts")
    helpers += "transfer = address => address;\n"
    if nested:
        imports, body = helpers.split("let transfer", 1)
        source = imports + source.replace("work() {\n", "work() {\nlet transfer" + body)
    else:
        source = helpers + source
    unit = unit_named(run_report(tmp_path, source, ".ts"), "<module>.work")

    assert "network" not in unit["effect_domains"]
    assert unit["coefficient"] < THRESHOLD
