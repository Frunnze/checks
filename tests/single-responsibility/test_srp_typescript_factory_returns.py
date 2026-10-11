import pytest
from srp_support import run_report, unit_named

IMPORTS = 'import { Pool } from "pg";\nimport * as fs from "node:fs";\n'
WORK_BODY = (
    "  await db.query(path);\n"
    "  fs.readFileSync(path);\n"
)
MODULE_FUNCTION = (
    "function connection(): Pool {\n"
    "  return new Pool();\n"
    "}\n"
    "export async function work(path: string) {\n"
    "  const db = connection();\n" + WORK_BODY + "}\n"
)
MODULE_ARROW = (
    "const connection = (): Pool => new Pool();\n"
    "export async function work(path: string) {\n"
    "  const db = connection();\n" + WORK_BODY + "}\n"
)
ASYNC_MODULE_FUNCTION = (
    "async function connection(): Promise<Pool> {\n"
    "  return new Pool();\n"
    "}\n"
    "export async function work(path: string) {\n"
    "  const db = await connection();\n" + WORK_BODY + "}\n"
)
NESTED_FUNCTION = (
    "export async function work(path: string) {\n"
    "  function connection(): Pool {\n"
    "    return new Pool();\n"
    "  }\n"
    "  const db = connection();\n" + WORK_BODY + "}\n"
)
METHOD = (
    "export class Exporter {\n"
    "  private connection(): Pool {\n"
    "    return new Pool();\n"
    "  }\n"
    "  async work(path: string) {\n"
    "    const db = this.connection();\n"
    "    await db.query(path);\n"
    "    fs.readFileSync(path);\n"
    "  }\n"
    "}\n"
)


@pytest.mark.parametrize(
    "source, unit",
    [
        (MODULE_FUNCTION, "<module>.work"),
        (MODULE_ARROW, "<module>.work"),
        (ASYNC_MODULE_FUNCTION, "<module>.work"),
        (NESTED_FUNCTION, "<module>.work"),
        (METHOD, "<module>.Exporter.work"),
    ],
    ids=["function", "arrow", "async", "nested", "method"],
)
def test_factory_return_types_bind_the_built_client(tmp_path, source, unit):
    report = run_report(tmp_path, IMPORTS + source, ".ts")

    assert unit_named(report, unit)["entities"] == [
        "filesystem",
        "persistence",
    ]
