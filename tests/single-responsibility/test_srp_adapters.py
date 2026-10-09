import json
import subprocess
import sys

import pytest
from srp_support import (
    CHECK,
    THRESHOLD,
    mixed_function,
    run_report,
    unit_named,
    write_split_project,
)


@pytest.mark.parametrize("suffix", [".py", ".ts", ".tsx"])
def test_comments_do_not_inflate_the_coefficient(tmp_path, suffix):
    source = mixed_function(suffix)
    marker = "#" if suffix == ".py" else "//"
    padded = source.replace("\n", "\n" + marker + " explanation\n\n")

    assert (
        run_report(tmp_path, source, suffix)["coefficient"]
        == run_report(
            tmp_path,
            padded,
            suffix,
        )["coefficient"]
    )


def test_docstrings_and_annotations_do_not_count_as_work(tmp_path):
    source = (
        "def identity(value: tuple[int, str]) -> tuple[int, str]:\n"
        '    """' + "\n".join(["details"] * 100) + '\n    """\n'
        "    return value\n"
    )
    unit = unit_named(run_report(tmp_path, source), "<module>.identity")

    assert unit["metrics"]["lines"] == 1
    assert unit["metrics"]["statements"] == 1
    assert unit["metrics"]["resources"] == []


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_nested_functions_are_measured_in_their_own_scope(tmp_path, suffix):
    inner = mixed_function(suffix)
    if suffix == ".py":
        imports, body = inner.split("def work():", 1)
        source = (
            imports
            + "def outer():\n    def work():"
            + body.replace("\n", "\n    ")
            + "\n    return work\n"
        )
    else:
        imports, body = inner.split("async function work()", 1)
        source = (
            imports
            + "function outer() {\nconst work = async () =>"
            + body
            + "return work;\n}"
        )
    report = run_report(tmp_path, source, suffix)

    assert unit_named(report, "<module>.outer")["coefficient"] < THRESHOLD
    assert unit_named(report, "<module>.outer.work")["coefficient"] >= THRESHOLD


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_import_aliases_preserve_effect_detection(tmp_path, suffix):
    source = mixed_function(suffix)
    if suffix == ".py":
        alias = (
            source.replace("import httpx", "import httpx as remote")
            .replace("httpx.", "remote.")
            .replace("import Path", "import Path as File")
            .replace("Path(", "File(")
        )
    else:
        alias = source.replace("axios", "remote").replace(
            'from "remote"', 'from "axios"'
        )
        alias = alias.replace("as fs", "as disk").replace("fs.", "disk.")

    assert (
        run_report(tmp_path, source, suffix)["coefficient"]
        == run_report(
            tmp_path,
            alias,
            suffix,
        )["coefficient"]
    )


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_shadowed_import_names_are_not_assumed_to_be_library_calls(tmp_path, suffix):
    source = mixed_function(suffix)
    if suffix == ".py":
        source = source.replace("def work():", "def work(httpx, Path):")
    else:
        source = source.replace("work()", "work(axios, fs)")
    report = run_report(tmp_path, source, suffix)

    assert not report["failed"]
    assert unit_named(report, "<module>.work")["effect_domains"] == {}


def test_python_assignment_and_context_manager_aliases(tmp_path):
    source = (
        "import sqlite3\nfrom pathlib import Path\n"
        "def save():\n    db = sqlite3.connect(':memory:')\n"
        "    db.execute('SELECT 1')\n    db.commit()\n"
        "    with open('one') as stream:\n        stream.read()\n"
        "    file = Path('two')\n    file.write_text('hello')\n"
    )
    unit = unit_named(run_report(tmp_path, source), "<module>.save")

    assert set(unit["effect_domains"]) == {"persistence", "filesystem"}
    assert "builtins.open.read" in unit["effect_domains"]["filesystem"]


def test_typescript_new_and_annotated_dependency_aliases(tmp_path):
    source = (
        'import {Client} from "pg";\n'
        "async function load(injected: Client) {\n"
        '  const db = new Client();\n  db.query("SELECT 1");\n'
        '  injected.query("SELECT 2");\n}\n'
    )
    unit = unit_named(run_report(tmp_path, source, ".ts"), "<module>.load")

    assert unit["effect_domains"] == {"persistence": ["pg.Client.query"]}


@pytest.mark.parametrize(
    "suffix, source",
    [
        (".py", "def broken(:\n"),
        (".ts", "function broken( {"),
        (".tsx", "const view = <div>"),
    ],
)
def test_syntax_errors_fail_closed_without_a_successful_json_report(
    tmp_path, suffix, source
):
    path = tmp_path / ("broken" + suffix)
    path.write_text(source)
    result = subprocess.run(
        [sys.executable, str(CHECK / "srp_check.py"), "--json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "SRP analysis error" in result.stderr
    assert str(path) in result.stderr
    assert not result.stdout


def test_json_order_is_deterministic_and_maximum_is_not_diluted(tmp_path):
    write_split_project(tmp_path, ".py")
    for i in range(5):
        (tmp_path / f"small{i}.py").write_text("def identity(x):\n    return x\n")
    command = [sys.executable, str(CHECK / "srp_check.py"), "--json", str(tmp_path)]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    second = subprocess.run(command, capture_output=True, text=True, check=False)

    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["coefficient"] == 0.5
