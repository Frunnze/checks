import json
import sys
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

from dependency_analyser_settings import dependency_analyser_configuration
from frameworks import preset_tool_section
from phpstan_settings import (
    derived_parameters,
    phpstan_configuration,
    scan_root_flag,
)
from settings import check_settings, read_configuration
from settings_validation import (
    Configuration,
    ConfigurationError,
    as_list,
    as_table,
    validate_known_keys,
)

TOOLKIT_DIRECTORY = Path(__file__).resolve().parent.parent
LINTERS_DIRECTORY = TOOLKIT_DIRECTORY / "checks" / "stable" / "linters"
PRESETS_MODULE = LINTERS_DIRECTORY / "typescript" / "eslint-presets.mjs"
BASE_RULESET = LINTERS_DIRECTORY / "php" / "phpcs-base.xml"
STRICT_NEON = (
    TOOLKIT_DIRECTORY / "checks" / "stable" / "strict-typing" / "php"
    / "phpstan.neon"
)
DEAD_CODE_NEON = (
    TOOLKIT_DIRECTORY / "checks" / "stable" / "dead-code" / "php"
    / "phpstan-dead-code.neon"
)
ESLINT_PRESETS = frozenset({"solid"})
ESLINT_KEYS = {"presets", "rules", "overrides"}
PHPCS_KEYS = {
    "standard",
    "exclude",
    "exclude-patterns",
    "properties",
    "config",
}
DEFAULT_PHPCS_STANDARD = "PSR12"
ESLINT_MODULE = """import {{ presets, typescriptConfigFor }}
  from {presets_module};

const packageDirectory = {package_directory};
const chosenPresets = {chosen_presets};
const userConfigs = {user_configs};
const presetConfigs = chosenPresets.map((name) => presets[name]);
const configs = typescriptConfigFor(packageDirectory, presetConfigs);

export default [
  ...configs.map((config) => ({{ ...config, basePath: packageDirectory }})),
  ...userConfigs,
];
"""


def eslint_configuration(
    section: dict[str, object], presets_module: Path, package: Path
) -> str:
    validate_known_keys("eslint", section, ESLINT_KEYS)
    chosen_presets = as_list("eslint.presets", section.get("presets", []))

    for preset_name in chosen_presets:
        if preset_name not in ESLINT_PRESETS:
            choices = ", ".join(sorted(ESLINT_PRESETS))
            message = f"eslint.presets: {preset_name} is not one of {choices}"
            raise ConfigurationError(message)

    user_configs: list[dict[str, object]] = []
    rules = as_table("eslint.rules", section.get("rules", {}))

    if rules:
        user_configs.append({"basePath": str(package), "rules": rules})

    for override in as_list("eslint.overrides", section.get("overrides", [])):
        override_table = as_table("eslint.overrides", override)
        user_configs.append({"basePath": str(package), **override_table})

    return ESLINT_MODULE.format(
        presets_module=json.dumps(str(presets_module)),
        package_directory=json.dumps(str(package)),
        chosen_presets=json.dumps(chosen_presets),
        user_configs=json.dumps(user_configs),
    )


def phpcs_property(name: str, property_value: object) -> ElementTree.Element:
    property_element = ElementTree.Element("property", name=name)

    if isinstance(property_value, list):
        property_element.set("type", "array")

        for element_value in cast("list[object]", property_value):
            _ = ElementTree.SubElement(
                property_element, "element", value=str(element_value)
            )

        return property_element

    if isinstance(property_value, bool):
        property_element.set("value", str(property_value).lower())

        return property_element

    property_element.set("value", str(property_value))

    return property_element


def add_sniff_properties(
    ruleset: ElementTree.Element, section: dict[str, object]
) -> None:
    sniff_properties = as_table(
        "phpcs.properties", section.get("properties", {})
    )

    for sniff_name, properties in sniff_properties.items():
        sniff_rule = ElementTree.SubElement(ruleset, "rule", ref=sniff_name)
        properties_element = ElementTree.SubElement(sniff_rule, "properties")
        property_table = as_table(f"phpcs.properties.{sniff_name}", properties)

        for property_name, property_value in property_table.items():
            properties_element.append(
                phpcs_property(property_name, property_value)
            )


def add_excluded_paths(
    ruleset: ElementTree.Element, section: dict[str, object]
) -> None:
    excluded_paths = as_table(
        "phpcs.exclude-patterns", section.get("exclude-patterns", {})
    )

    for sniff_name, patterns in excluded_paths.items():
        sniff_rule = ElementTree.SubElement(ruleset, "rule", ref=sniff_name)
        setting_name = f"phpcs.exclude-patterns.{sniff_name}"

        for pattern in as_list(setting_name, patterns):
            pattern_element = ElementTree.SubElement(
                sniff_rule, "exclude-pattern"
            )
            pattern_element.text = str(pattern)


def phpcs_configuration(
    section: dict[str, object], base_ruleset: Path
) -> str:
    validate_known_keys("phpcs", section, PHPCS_KEYS)
    ruleset = ElementTree.Element("ruleset", name="checks")
    config_values = as_table("phpcs.config", section.get("config", {}))

    for config_name, config_value in config_values.items():
        _ = ElementTree.SubElement(
            ruleset, "config", name=config_name, value=str(config_value)
        )

    standard = str(section.get("standard", DEFAULT_PHPCS_STANDARD))
    standard_rule = ElementTree.SubElement(ruleset, "rule", ref=standard)

    for excluded_sniff in as_list("phpcs.exclude", section.get("exclude", [])):
        _ = ElementTree.SubElement(
            standard_rule, "exclude", name=str(excluded_sniff)
        )

    _ = ElementTree.SubElement(ruleset, "rule", ref=str(base_ruleset))
    add_sniff_properties(ruleset, section)
    add_excluded_paths(ruleset, section)

    return ElementTree.tostring(ruleset, encoding="unicode")


def tool_section(
    configuration: Configuration,
    check_name: str,
    tool_name: str,
    package: Path,
) -> dict[str, object]:
    settings = check_settings(configuration, check_name)
    written = as_table(f"checks.{check_name}.{tool_name}", settings[tool_name])
    preset = preset_tool_section(package, check_name, tool_name)

    return {**preset, **written}


def phpstan_for(
    configuration: Configuration,
    check_name: str,
    default_neon: Path,
    locations: tuple[Path, Path],
) -> str:
    package, project_root = locations
    settings = check_settings(configuration, check_name)
    section = tool_section(configuration, check_name, "phpstan", package)
    scan_root_flag(section)
    excluded_paths: list[object] = []

    if check_name == "strict-typing":
        excluded_paths = as_list(
            "checks.strict-typing.whitelist", settings["whitelist"]
        )

    derived = derived_parameters(
        section, package, project_root, excluded_paths
    )

    return phpstan_configuration(section, default_neon, package, derived)


def generated_configuration(
    configuration_path: Path,
    tool_name: str,
    locations: tuple[Path, Path],
) -> str:
    configuration = read_configuration(configuration_path)
    package = locations[0]

    if tool_name == "eslint":
        section = tool_section(configuration, "linters", "eslint", package)

        return eslint_configuration(section, PRESETS_MODULE, package)

    if tool_name == "phpcs":
        section = tool_section(configuration, "linters", "phpcs", package)

        return phpcs_configuration(section, BASE_RULESET)

    if tool_name == "composer-dependency-analyser":
        section = tool_section(
            configuration,
            "unused-deps",
            "composer-dependency-analyser",
            package,
        )

        return dependency_analyser_configuration(section)

    if tool_name == "phpstan":
        return phpstan_for(
            configuration, "strict-typing", STRICT_NEON, locations
        )

    if tool_name == "phpstan-dead-code":
        return phpstan_for(
            configuration, "dead-code", DEAD_CODE_NEON, locations
        )

    message = f"no generated configuration for {tool_name}"
    raise ConfigurationError(message)


def main(arguments: list[str]) -> int:
    configuration_path = Path(arguments[0])
    tool_name = arguments[1]
    package = Path(arguments[2]).resolve()
    project_root = Path(arguments[3]).resolve()

    try:
        generated = generated_configuration(
            configuration_path, tool_name, (package, project_root)
        )
    except (OSError, ValueError) as error:
        _ = sys.stderr.write(f"pre-commit: checks.toml: {error}\n")
        return 1

    _ = sys.stdout.write(generated)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
