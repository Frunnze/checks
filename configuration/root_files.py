import sys
from pathlib import Path

from frameworks import framework_of

ROOT_FILE_FRAMEWORK = "wordpress"
ROOT_FILE_PATTERN = "*.php"


def root_php_files(project_root: Path) -> list[str]:
    root_files = sorted(project_root.glob(ROOT_FILE_PATTERN))

    return [str(path) for path in root_files]


def package_root_files(package: Path, project_root: Path) -> list[str]:
    if framework_of(package) != ROOT_FILE_FRAMEWORK:
        return []

    root_file_names: list[str] = []

    for root_file in root_php_files(project_root):
        root_file_names.append(Path(root_file).name)

    return root_file_names


def main(arguments: list[str]) -> int:
    package = Path(arguments[0]).resolve()
    project_root = Path(arguments[1]).resolve()

    try:
        owned_files = package_root_files(package, project_root)
    except (OSError, ValueError) as error:
        _ = sys.stderr.write(f"checks: {package}/composer.json: {error}\n")
        return 1

    for owned_file in owned_files:
        _ = sys.stdout.write(f"{owned_file}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
