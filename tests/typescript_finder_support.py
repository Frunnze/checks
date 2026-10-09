import subprocess
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parent.parent
CHECKS = TOOLKIT / "checks"
TYPESCRIPT_MODULE = TOOLKIT / "node_modules" / "typescript"


def report_from(
    finder: Path, tmp_path: Path, files: dict[str, str]
) -> list[str]:
    written: list[str] = []

    for relative, source in files.items():
        module = tmp_path / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")
        written.append(relative)

    finished = subprocess.run(
        ["node", str(finder), str(TYPESCRIPT_MODULE)],
        input="\n".join(written),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()
