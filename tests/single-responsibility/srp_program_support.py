import tempfile
from pathlib import Path

from srp_support import analyze

CLIENTS = {
    "network": (
        "import requests",
        "requests.Session()",
        "requests.Session",
        ".get(target)",
    ),
    "persistence": (
        "import sqlite3",
        "sqlite3.connect(target)",
        "sqlite3.Connection",
        ".execute('select 1')",
    ),
    "email": (
        "import smtplib",
        "smtplib.SMTP(target)",
        "smtplib.SMTP",
        ".send_message(None)",
    ),
    "ai": (
        "import openai",
        "openai.OpenAI()",
        "openai.OpenAI",
        ".chat.completions.create(model=target)",
    ),
    "queue": (
        "import celery",
        "celery.Celery('jobs')",
        "celery.Celery",
        ".send_task(target)",
    ),
    "process": (
        "import subprocess",
        "subprocess.Popen([target])",
        "subprocess.Popen",
        ".communicate()",
    ),
}


def unit_entities(
    files: dict[str, str], path: str, kind: str, name: str
) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for relative, text in files.items():
            source = root / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(text, encoding="utf-8")
        report = analyze(sorted(root.rglob("*.py")), "node", None, (), [root])
    for file in report["files"]:
        if Path(file["path"]).relative_to(root).as_posix() != path:
            continue
        for unit in file["units"]:
            if unit["kind"] == kind and unit["name"] == name:
                return unit["entities"]
    raise AssertionError(f"no {kind} {name} in {path}")
