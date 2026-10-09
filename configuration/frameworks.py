import json
import tomllib
from pathlib import Path
from typing import cast

from settings_validation import TOOLKIT_DIRECTORY, as_table

FRAMEWORKS_DIRECTORY = Path(__file__).resolve().parent / "frameworks"
FRAMEWORK_OF_COMPOSER_TYPE = {
    "wordpress-plugin": "wordpress",
    "wordpress-theme": "wordpress",
}
TOOLKIT_PLACEHOLDER = "{toolkit}"


def framework_of(package: Path) -> str | None:
    manifest_path = package / "composer.json"

    if not manifest_path.is_file():
        return None

    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = cast("object", json.loads(manifest_text))
    package_type = as_table("composer.json", manifest).get("type")

    return FRAMEWORK_OF_COMPOSER_TYPE.get(str(package_type))


def preset_tool_section(
    package: Path, check_name: str, tool_name: str
) -> dict[str, object]:
    framework = framework_of(package)

    if framework is None:
        return {}

    preset_path = FRAMEWORKS_DIRECTORY / f"{framework}.toml"
    preset_text = preset_path.read_text(encoding="utf-8")
    toolkit_text = preset_text.replace(
        TOOLKIT_PLACEHOLDER, str(TOOLKIT_DIRECTORY)
    )
    preset = cast("dict[str, object]", tomllib.loads(toolkit_text))
    checks = as_table("checks", preset.get("checks", {}))
    check = as_table(check_name, checks.get(check_name, {}))

    return as_table(tool_name, check.get(tool_name, {}))
