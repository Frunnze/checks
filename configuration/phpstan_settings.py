import json
import re
from pathlib import Path
from typing import cast

from settings_validation import (
    ConfigurationError,
    as_list,
    as_table,
    validate_known_keys,
)

PHPSTAN_KEYS = {"includes", "parameters", "scan-root-files"}
PHP_REQUIREMENT = re.compile(r"(\d+)\.(\d+)")
MAJOR_VERSION_FACTOR = 10_000
MINOR_VERSION_FACTOR = 100


def php_version_of(package: Path) -> int | None:
    manifest_path = package / "composer.json"

    if not manifest_path.is_file():
        return None

    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = cast("object", json.loads(manifest_text))
    manifest_table = as_table("composer.json", manifest)
    requirements = as_table(
        "composer.json require", manifest_table.get("require", {})
    )
    php_requirement = str(requirements.get("php", ""))
    versions: list[tuple[int, int]] = []

    for version_match in PHP_REQUIREMENT.finditer(php_requirement):
        major = int(version_match.group(1))
        minor = int(version_match.group(2))
        versions.append((major, minor))

    if not versions:
        return None

    major_version, minor_version = min(versions)

    return (
        major_version * MAJOR_VERSION_FACTOR
        + minor_version * MINOR_VERSION_FACTOR
    )


def derived_parameters(
    section: dict[str, object],
    package: Path,
    project_root: Path,
    excluded_paths: list[object],
) -> dict[str, object]:
    parameters: dict[str, object] = {}
    php_version = php_version_of(package)

    if php_version is not None:
        parameters["phpVersion"] = php_version

    if section.get("scan-root-files") is True:
        root_files = sorted(project_root.glob("*.php"))
        parameters["scanFiles"] = [str(path) for path in root_files]

    if excluded_paths:
        parameters["excludePaths"] = [
            str(project_root / str(path)) for path in excluded_paths
        ]

    return parameters


def phpstan_configuration(
    section: dict[str, object],
    default_neon: Path,
    package: Path,
    derived: dict[str, object],
) -> str:
    validate_known_keys("phpstan", section, PHPSTAN_KEYS)
    includes = [str(default_neon)]

    for include in as_list("phpstan.includes", section.get("includes", [])):
        includes.append(str(package / str(include)))

    written_parameters = as_table(
        "phpstan.parameters", section.get("parameters", {})
    )
    parameters = {**derived, **written_parameters}
    generated: dict[str, object] = {"includes": includes}

    if parameters:
        generated["parameters"] = parameters

    return json.dumps(generated, indent=2)


def scan_root_flag(section: dict[str, object]) -> None:
    flag = section.get("scan-root-files", False)

    if not isinstance(flag, bool):
        message = "phpstan.scan-root-files must be true or false"
        raise ConfigurationError(message)
