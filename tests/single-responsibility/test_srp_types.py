import pytest
from srp_support import THRESHOLD, mixed_function, run_report, unit_named


@pytest.mark.parametrize(
    "annotation",
    [
        "Annotated[httpx.Client, 'injected']",
        "Optional[httpx.Client]",
        "httpx.Client | None",
        "Union[httpx.Client, None]",
        "'httpx.Client'",
        "'Annotated[httpx.Client, 1]'",
    ],
)
def test_python_explicit_dependency_types_keep_mixed_work_visible(tmp_path, annotation):
    source = "from typing import Annotated, Optional, Union\n" + mixed_function()
    source = source.replace("def work():", f"def work(client: {annotation}):")
    source = source.replace("httpx.get(", "client.get(").replace(
        "httpx.post(", "client.post("
    )
    unit = unit_named(run_report(tmp_path, source), "<module>.work")

    assert unit["coefficient"] >= THRESHOLD
    assert unit["effect_domains"]["network"] == [
        "httpx.Client.get",
        "httpx.Client.post",
    ]


def test_python_annotated_aliases_resolve_without_executing_metadata(tmp_path):
    source = (
        "from typing import Annotated\nimport httpx\n"
        "Remote = Annotated[httpx.Client, fail_if_executed()]\n"
        + mixed_function()
        .replace("def work():", "def work(client: Remote):")
        .replace("httpx.get(", "client.get(")
        .replace("httpx.post(", "client.post(")
    )
    assert (
        unit_named(run_report(tmp_path, source), "<module>.work")["coefficient"]
        >= THRESHOLD
    )


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_ambiguous_dependency_union_cannot_supply_library_evidence(tmp_path, suffix):
    source = (
        "import httpx\ndef work(client: httpx.Client | Unknown):\n    client.get('a')\n"
        if suffix == ".py"
        else 'import type {AxiosInstance} from "axios";\n'
        "function work(client: AxiosInstance | Unknown) { client.get('a'); }\n"
    )
    assert (
        unit_named(run_report(tmp_path, source, suffix), "<module>.work")[
            "effect_domains"
        ]
        == {}
    )


@pytest.mark.parametrize(
    "annotation",
    ["AxiosInstance", "AxiosInstance | null | undefined", "(AxiosInstance)"],
)
def test_typescript_typed_dependency_parameters(tmp_path, annotation):
    source = 'import type {AxiosInstance} from "axios";\n' + mixed_function(".ts")
    source = source.replace("work()", f"work(client: {annotation})")
    source = source.replace("axios.get(", "client.get(").replace(
        "axios.post(", "client.post("
    )
    unit = unit_named(run_report(tmp_path, source, ".ts"), "<module>.work")

    assert unit["coefficient"] >= THRESHOLD
    assert unit["effect_domains"]["network"] == [
        "axios.AxiosInstance.get",
        "axios.AxiosInstance.post",
    ]


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_explicit_local_dependency_types_resolve_unknown_factories(tmp_path, suffix):
    source = (
        "import httpx\ndef work():\n    client: httpx.Client = provide()\n    client.get('url')\n"
        if suffix == ".py"
        else 'import type {AxiosInstance} from "axios";\n'
        "function work() { const client: AxiosInstance = provide(); client.get('url'); }\n"
    )
    assert (
        "network"
        in unit_named(run_report(tmp_path, source, suffix), "<module>.work")[
            "effect_domains"
        ]
    )


@pytest.mark.parametrize("suffix", [".py", ".ts", ".tsx"])
@pytest.mark.parametrize("form", ["declaration", "constructor", "initializer"])
def test_dependency_fields_expose_independent_mixed_implementations(
    tmp_path, suffix, form
):
    if suffix == ".py":
        imports, body = mixed_function().split("def work():", 1)
        declaration = {
            "declaration": "    client: httpx.Client\n",
            "constructor": "    def __init__(self, client: httpx.Client):\n        self.client = client\n",
            "initializer": "    def __init__(self):\n        self.client = httpx.Client()\n",
        }[form]
        body = body.replace("httpx.get(", "self.client.get(").replace(
            "httpx.post(", "self.client.post("
        )
        source = (
            imports
            + "class Worker:\n"
            + declaration
            + "    def work(self):"
            + body.replace("\n", "\n    ")
        )
    else:
        imports, body = mixed_function(suffix).split("async function work()", 1)
        declaration = {
            "declaration": "client: AxiosInstance;\n",
            "constructor": "constructor(private client: AxiosInstance) {}\n",
            "initializer": "client = new Axios();\n",
        }[form]
        body = body.replace("axios.get(", "this.client.get(").replace(
            "axios.post(", "this.client.post("
        )
        source = (
            imports
            + 'import {Axios, type AxiosInstance} from "axios";\nclass Worker {\n'
            + declaration
            + "async work()"
            + body
            + "}\n"
        )
    unit = unit_named(run_report(tmp_path, source, suffix), "<module>.Worker.work")

    assert unit["coefficient"] >= THRESHOLD


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_mutable_constructor_inferences_abstain_when_other_methods_replace_fields(
    tmp_path, suffix
):
    source = (
        "import httpx\nclass Worker:\n"
        "    def __init__(self):\n        self.client = httpx.Client()\n"
        "    def replace(self, value):\n        self.client = value\n"
        "    def work(self):\n        self.client.get('url')\n"
        if suffix == ".py"
        else 'import {Axios} from "axios";\nclass Worker {\n'
        "client = new Axios();\nreplace(value) { this.client = value; }\n"
        "work() { this.client.get('url'); }\n}\n"
    )
    assert (
        unit_named(run_report(tmp_path, source, suffix), "<module>.Worker.work")[
            "effect_domains"
        ]
        == {}
    )
