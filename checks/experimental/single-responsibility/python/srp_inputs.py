import json
import shutil
import subprocess
from pathlib import Path

CHECK_DIRECTORY = Path(__file__).resolve().parent.parent
TOOLKIT_DIRECTORY = CHECK_DIRECTORY.parents[2]
PRUNED = {"node_modules", "__pycache__", "dist", "build", ".git", ".venv"}
SUFFIXES = {".py", ".ts", ".tsx", ".mts", ".cts"}


def raise_walk_error(error: OSError) -> None:
    raise error


def source_paths(inputs: list[str]) -> list[Path]:
    paths: dict[Path, Path] = {}
    for name in inputs:
        path = Path(name)
        if not path.exists():
            raise ValueError(f"source path does not exist: {path}")
        if path.is_file():
            if path.suffix not in SUFFIXES:
                raise ValueError(f"unsupported source file: {path}")
            paths.setdefault(path.resolve(), path)
        else:
            for directory, subdirs, files in path.walk(on_error=raise_walk_error):
                subdirs[:] = [name for name in subdirs if name not in PRUNED]
                for name in files:
                    if Path(name).suffix in SUFFIXES:
                        source = directory / name
                        paths.setdefault(source.resolve(), source)
    return sorted(paths.values())


def typescript_facts(
    paths: list[Path], node: str, module: str | None, tsconfig=None
) -> list[dict]:
    if not paths:
        return []
    if not module:
        candidates = [
            parent / "node_modules/typescript"
            for path in paths
            for parent in path.resolve().parents
        ]
        candidates.append(TOOLKIT_DIRECTORY / "node_modules/typescript")
        module = next(
            (str(candidate) for candidate in candidates if candidate.is_dir()), ""
        )
    if not shutil.which(node) or not module or not Path(module).is_dir():
        raise ValueError(
            "Node/TypeScript is missing - run ./install.sh or provide --node and --typescript"
        )
    result = subprocess.run(
        [
            node,
            str(CHECK_DIRECTORY / "typescript" / "typescript_facts.js"),
            str(Path(module).resolve()),
            str(Path(tsconfig).resolve()) if tsconfig else "",
        ],
        input=json.dumps([str(path) for path in paths]),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return json.loads(result.stdout)
