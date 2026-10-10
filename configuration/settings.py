import json
import re
import sys
import tomllib
from pathlib import Path
from typing import cast

from settings_validation import (
    CHECK_ORDER,
    CHECKS_SETTING,
    EXPERIMENTAL_DIRECTORY,
    NUMBER_OPTIONS,
    SOURCE_SETTING,
    STABLE_DIRECTORY,
    TOOL_OPTIONS,
    TOOLKIT_DIRECTORY,
    Configuration,
    ConfigurationError,
    as_table,
    validate_check_name,
    validate_configuration,
)

DEFAULT_SETTINGS: Configuration = {
    "python_environment": ".venv",
    "stable": "pre-commit",
    "checks": {},
}
DEFAULT_NUMBERS = {"max-lines": 300, "fail-under": 100}
CHECK_DEFAULTS: dict[str, object] = {"scope": "repository", "whitelist": []}
OFF = "off"
BOTH_HOOKS = "both"
EVERY_STAGE = "all"
ENABLED_CHECKS_SETTING = "enabled_check_directories"
BARE_TOML_KEY = re.compile(r"[A-Za-z0-9_-]+")
ERROR_PREFIX = "pre-commit: checks.toml:"
DELETE_CHARACTER = "\x7f"
ESCAPED_DELETE = "\\u007f"


def with_defaults(written_settings: Configuration) -> Configuration:
    return {**DEFAULT_SETTINGS, **written_settings}


def read_configuration(configuration_path: Path) -> Configuration:
    with configuration_path.open("rb") as configuration_file:
        written_settings = tomllib.load(configuration_file)

    configuration = with_defaults(written_settings)
    known_settings = {*DEFAULT_SETTINGS, SOURCE_SETTING}
    validate_configuration(configuration, known_settings)

    return configuration


def is_stable(check_name: str) -> bool:
    return (STABLE_DIRECTORY / check_name).is_dir()


def check_settings(
    configuration: Configuration, check_name: str
) -> dict[str, object]:
    checks = as_table(CHECKS_SETTING, configuration[CHECKS_SETTING])
    written = as_table(f"checks.{check_name}", checks.get(check_name, {}))
    default_when = configuration["stable"] if is_stable(check_name) else OFF
    settings: dict[str, object] = {
        **CHECK_DEFAULTS,
        "when": default_when,
        SOURCE_SETTING: configuration[SOURCE_SETTING],
    }

    if check_name in NUMBER_OPTIONS:
        option_name = NUMBER_OPTIONS[check_name][0]
        settings[option_name] = DEFAULT_NUMBERS[option_name]

    for tool_name in TOOL_OPTIONS.get(check_name, frozenset()):
        settings[tool_name] = {}

    settings.update(written)

    return settings


def runs_at(when: object, stage: str) -> bool:
    if when == OFF:
        return False

    if stage == EVERY_STAGE:
        return True

    return when in {stage, BOTH_HOOKS}


def enabled_check_directories(
    configuration: Configuration, stage: str
) -> list[Path]:
    enabled_directories: list[Path] = []

    for check_name in CHECK_ORDER:
        when = check_settings(configuration, check_name)["when"]

        if not runs_at(when, stage):
            continue

        if is_stable(check_name):
            check_directory = STABLE_DIRECTORY / check_name
        else:
            check_directory = EXPERIMENTAL_DIRECTORY / check_name

        enabled_directories.append(
            check_directory.relative_to(TOOLKIT_DIRECTORY)
        )

    return enabled_directories


def setting_value(configuration: Configuration, setting_name: str) -> object:
    section_name, _, key = setting_name.partition(".")

    if section_name == ENABLED_CHECKS_SETTING:
        directories = enabled_check_directories(configuration, key)

        return [str(directory) for directory in directories]

    if section_name == CHECKS_SETTING:
        check_name, _, field = key.partition(".")
        validate_check_name(check_name)
        settings = check_settings(configuration, check_name)

        if field not in settings:
            message = f"no setting named {setting_name}"
            raise ConfigurationError(message)

        return settings[field]

    if setting_name in configuration:
        return configuration[setting_name]

    message = f"no setting named {setting_name}"
    raise ConfigurationError(message)


def toml_key(key: str) -> str:
    if BARE_TOML_KEY.fullmatch(key):
        return key

    return toml_value(key)


def toml_value(written_value: object) -> str:
    json_text = json.dumps(written_value, ensure_ascii=False)

    return json_text.replace(DELETE_CHARACTER, ESCAPED_DELETE)


def toml_override_lines(
    table: dict[str, object], key_prefix: str
) -> list[str]:
    lines: list[str] = []

    for key, nested_value in table.items():
        dotted_key = f"{key_prefix}{toml_key(key)}"

        if isinstance(nested_value, dict):
            nested_table = cast("dict[str, object]", nested_value)
            lines.extend(toml_override_lines(nested_table, f"{dotted_key}."))
        else:
            lines.append(f"{dotted_key} = {toml_value(nested_value)}")

    return lines


def printable_line(entry: object) -> str:
    if isinstance(entry, dict):
        return json.dumps(entry, sort_keys=True)

    return str(entry)


def setting_lines(
    configuration: Configuration, setting_name: str
) -> list[str]:
    found_value = setting_value(configuration, setting_name)

    if isinstance(found_value, dict):
        table = cast("dict[str, object]", found_value)

        return toml_override_lines(table, "")

    if not isinstance(found_value, list):
        return [printable_line(found_value)]

    lines: list[str] = []

    for entry in cast("list[object]", found_value):
        lines.append(printable_line(entry))

    return lines


def main(arguments: list[str]) -> int:
    configuration_path = Path(arguments[0])
    setting_name = arguments[1]

    try:
        configuration = read_configuration(configuration_path)
        lines = setting_lines(configuration, setting_name)
    except (OSError, ValueError) as error:
        _ = sys.stderr.write(f"{ERROR_PREFIX} {error}\n")
        return 1

    for line in lines:
        _ = sys.stdout.write(f"{line}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
