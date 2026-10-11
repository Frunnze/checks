import pytest
from srp_support import run_project, unit_named

WORK = (
    'import { api } from "./api";\n'
    'import { storage } from "./storage";\n'
    "export async function work(id: string) {\n"
    "  const user = await api.getUser(id);\n"
    "  storage.save(String(user));\n"
    "}\n"
)
SERVICES = {
    "api": ('import axios from "axios";\n', "getUser", "axios.get(key)"),
    "storage": ("", "save", "localStorage.setItem(key, key)"),
}


def instance(name, method, body):
    return (
        f"class {name.title()} {{\n"
        f"  {method}(key: string) {{ return {body}; }}\n"
        "}\n"
        f"export const {name} = new {name.title()}();\n"
    )


def listed_instance(name, method, body):
    return (
        f"class {name.title()} {{\n"
        f"  {method}(key: string) {{ return {body}; }}\n"
        "}\n"
        f"const {name} = new {name.title()}();\n"
        f"export {{ {name} }};\n"
    )


def object_methods(name, method, body):
    return (
        f"export const {name} = {{\n"
        f"  {method}(key: string) {{ return {body}; }},\n"
        "};\n"
    )


def object_arrows(name, method, body):
    return (
        f"export const {name} = {{\n"
        f"  {method}: (key: string) => {body},\n"
        "};\n"
    )


def satisfied_object(name, method, body):
    return (
        f"export const {name} = {{\n"
        f"  {method}(key: string) {{ return {body}; }},\n"
        "} satisfies object;\n"
    )


@pytest.mark.parametrize(
    "service",
    [
        instance,
        listed_instance,
        object_methods,
        object_arrows,
        satisfied_object,
    ],
)
def test_exported_service_values_delegate_their_methods(tmp_path, service):
    for name, (imports, method, body) in SERVICES.items():
        source = imports + service(name, method, body)
        (tmp_path / f"{name}.ts").write_text(source)
    (tmp_path / "work.ts").write_text(WORK)

    report = run_project(tmp_path)

    work = unit_named(report, "<module>.work")
    assert work["entities"] == ["network", "persistence"]
    assert report["failed"]
