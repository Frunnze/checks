import pytest
from srp_support import mixed_function, run_report, unit_named


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_unimported_names_that_look_like_libraries_do_not_count(tmp_path, suffix):
    source = mixed_function(suffix)
    source = "\n".join(
        line
        for line in source.splitlines()
        if not line.startswith(("import ", "from "))
    )
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.work")

    assert unit["effect_domains"] == {}
    assert unit["coefficient"] < 0.8


@pytest.mark.parametrize(
    "suffix, source",
    [
        (
            ".py",
            (
                "def outer():\n    def open(value):\n        return value\n"
                "    return open('a')\n"
            ),
        ),
        (
            ".ts",
            (
                "function outer() {\n function fetch(value) { return value; }\n"
                "return fetch('a');\n}"
            ),
        ),
    ],
)
def test_local_function_declarations_shadow_implicit_builtins(tmp_path, suffix, source):
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.outer")

    assert unit["effect_domains"] == {}


def test_type_only_imports_resolve_injected_dependency_operations(tmp_path):
    source = (
        'import type {Client} from "pg";\n'
        "async function load(db: Client) {\n"
        '  db.query("SELECT 1");\n}\n'
    )
    unit = unit_named(run_report(tmp_path, source, ".ts"), "<module>.load")

    assert unit["effect_domains"] == {"persistence": ["pg.Client.query"]}


@pytest.mark.parametrize(
    "suffix, source, operation",
    [
        (
            ".py",
            (
                "import httpx\ndef work():\n    client = httpx\n"
                "    client = client.get('url')\n    client.post('other')\n"
            ),
            "httpx.get",
        ),
        (
            ".ts",
            (
                'import axios from "axios";\nfunction work() {\n'
                "  let client = axios;\n  client = client.get('url');\n"
                "  client.post('other');\n}\n"
            ),
            "axios.get",
        ),
    ],
)
def test_assignment_reads_the_previous_binding_before_replacing_it(
    tmp_path, suffix, source, operation
):
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.work")

    assert unit["effect_domains"] == {"network": [operation]}
    assert operation in unit["metrics"]["flow"][1]["calls"]


@pytest.mark.parametrize(
    "binding",
    [
        "try:\n        run()\n    except Exception as httpx:\n",
        "match value:\n        case httpx:\n",
        "match value:\n        case [*httpx]:\n",
        "match value:\n        case {**httpx}:\n",
    ],
)
@pytest.mark.parametrize("local_import", [False, True])
def test_python_exception_and_pattern_bindings_shadow_imports(
    tmp_path, binding, local_import
):
    declaration = (
        "def work(value):\n    import httpx\n"
        if local_import
        else "import httpx\ndef work(value):\n"
    )
    source = (
        declaration
        + "    "
        + binding
        + "            httpx.get('a')\n            httpx.post('b')\n"
    )
    unit = unit_named(run_report(tmp_path, source), "<module>.work")

    assert unit["effect_domains"] == {}


@pytest.mark.parametrize(
    "suffix, source, operation",
    [
        (
            ".py",
            "import httpx\nclient = httpx\ndef work():\n    client.get('url')\n",
            "httpx.get",
        ),
        (
            ".ts",
            (
                'import axios from "axios";\nconst client = axios;\n'
                "function work() { client.get('url'); }\n"
            ),
            "axios.get",
        ),
    ],
)
def test_module_aliases_are_visible_inside_functions(
    tmp_path, suffix, source, operation
):
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.work")

    assert unit["effect_domains"] == {"network": [operation]}
