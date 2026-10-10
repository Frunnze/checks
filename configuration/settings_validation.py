import datetime
import math
import re
from pathlib import Path, PurePosixPath
from typing import cast

type Configuration = dict[str, object]

TOOLKIT_DIRECTORY = Path(__file__).resolve().parent.parent
CHECKS_DIRECTORY = TOOLKIT_DIRECTORY / "checks"
STABLE_DIRECTORY = CHECKS_DIRECTORY / "stable"
EXPERIMENTAL_DIRECTORY = CHECKS_DIRECTORY / "experimental"
CHECK_ORDER = (
    "secrets",
    "file-length",
    "single-responsibility",
    "feature-isolation",
    "open-closed",
    "dependency-inversion",
    "definition-names",
    "nested-definitions",
    "duplicate-code",
    "dead-code",
    "linters",
    "unused-deps",
    "property-tests",
    "vulnerable-deps",
    "security-patterns",
    "strict-typing",
    "api-contract",
    "coverage",
)
UNSILENCEABLE_CHECKS = frozenset({"api-contract", "coverage", "unused-deps"})
WHEN_CHOICES = frozenset({"pre-commit", "pre-push", "both", "off"})
SCOPE_CHOICES = frozenset({"changed", "repository"})
COMMON_CHECK_KEYS = frozenset(
    {"when", "scope", "whitelist", "source_directories"}
)
NUMBER_OPTIONS: dict[str, tuple[str, int, int]] = {
    "file-length": ("max-lines", 1, 100_000),
    "coverage": ("fail-under", 0, 100),
}
TOOL_OPTIONS: dict[str, frozenset[str]] = {
    "linters": frozenset({"ruff", "eslint", "phpcs"}),
    "strict-typing": frozenset({"phpstan"}),
    "dead-code": frozenset({"phpstan"}),
    "unused-deps": frozenset({"composer-dependency-analyser"}),
}
SOURCE_SETTING = "source_directories"
ENVIRONMENT_SETTING = "python_environment"
UNSUPPORTED_FOLDER_NAME = re.compile(r"[\s*?\[\\]|^-")
CHECKS_SETTING = "checks"


class ConfigurationError(ValueError):
    pass


def as_list(setting_name: str, setting_value: object) -> list[object]:
    if not isinstance(setting_value, list):
        message = f"{setting_name} must be a list"
        raise ConfigurationError(message)

    return cast("list[object]", setting_value)


def as_table(setting_name: str, setting_value: object) -> dict[str, object]:
    if not isinstance(setting_value, dict):
        message = f"{setting_name} must be a table"
        raise ConfigurationError(message)

    return cast("dict[str, object]", setting_value)


def validate_choice(
    setting_name: str, chosen_value: object, choices: frozenset[str]
) -> None:
    if not isinstance(chosen_value, str) or chosen_value not in choices:
        listed_choices = ", ".join(sorted(choices))
        message = (
            f"{setting_name}: {chosen_value} is not one of {listed_choices}"
        )
        raise ConfigurationError(message)


def validate_known_keys(
    table_name: str, table: dict[str, object], known_keys: set[str]
) -> None:
    unknown_keys = sorted(set(table) - known_keys)

    if unknown_keys:
        message = f"{table_name}: unknown settings {', '.join(unknown_keys)}"
        raise ConfigurationError(message)


def validate_source_directories(source_directories: object) -> None:
    listed_directories = as_list(SOURCE_SETTING, source_directories)

    if not listed_directories:
        message = f"{SOURCE_SETTING} must not be empty"
        raise ConfigurationError(message)

    for source_directory in listed_directories:
        validate_source_directory(source_directory)


def validate_source_directory(source_directory: object) -> None:
    if not isinstance(source_directory, str):
        message = f"{SOURCE_SETTING} must hold strings"
        raise ConfigurationError(message)

    if not source_directory:
        message = f"{SOURCE_SETTING} must not hold an empty folder name"
        raise ConfigurationError(message)

    if UNSUPPORTED_FOLDER_NAME.search(source_directory):
        message = (
            f"{SOURCE_SETTING}: {source_directory} - folder names with"
            " whitespace, *, ?, [, \\ or a leading - are not supported"
        )
        raise ConfigurationError(message)

    folder = PurePosixPath(source_directory)

    if folder.is_absolute() or ".." in folder.parts:
        message = (
            f"{SOURCE_SETTING}: {source_directory} must be a folder inside"
            " the repository, relative to its root"
        )
        raise ConfigurationError(message)

    if folder.as_posix() != source_directory:
        message = (
            f"{SOURCE_SETTING}: write {source_directory} as"
            f" {folder.as_posix()}"
        )
        raise ConfigurationError(message)


def validate_plain_values(setting_name: str, setting_value: object) -> None:
    if isinstance(setting_value, (datetime.date, datetime.time)):
        message = f"{setting_name}: dates and times are not supported"
        raise ConfigurationError(message)

    if isinstance(setting_value, float) and not math.isfinite(setting_value):
        message = f"{setting_name}: inf and nan are not supported"
        raise ConfigurationError(message)

    if isinstance(setting_value, dict):
        table = cast("dict[str, object]", setting_value)

        for key, nested_value in table.items():
            validate_plain_values(f"{setting_name}.{key}", nested_value)

    if isinstance(setting_value, list):
        for nested_value in cast("list[object]", setting_value):
            validate_plain_values(setting_name, nested_value)


def validate_number_option(check_name: str, check: dict[str, object]) -> None:
    if check_name not in NUMBER_OPTIONS:
        return

    option_name, lowest, highest = NUMBER_OPTIONS[check_name]

    if option_name not in check:
        return

    setting_name = f"checks.{check_name}.{option_name}"
    option_value = check[option_name]
    is_flag = isinstance(option_value, bool)

    if is_flag or not isinstance(option_value, int):
        message = f"{setting_name} must be an integer"
        raise ConfigurationError(message)

    if not lowest <= option_value <= highest:
        message = f"{setting_name} must be between {lowest} and {highest}"
        raise ConfigurationError(message)


def allowed_check_keys(check_name: str) -> set[str]:
    allowed_keys = set(COMMON_CHECK_KEYS)
    allowed_keys.update(TOOL_OPTIONS.get(check_name, frozenset()))

    if check_name in NUMBER_OPTIONS:
        allowed_keys.add(NUMBER_OPTIONS[check_name][0])

    return allowed_keys


def validate_check(check_name: str, check_section: object) -> None:
    table_name = f"checks.{check_name}"
    check = as_table(table_name, check_section)
    validate_known_keys(table_name, check, allowed_check_keys(check_name))

    if "when" in check:
        validate_choice(f"{table_name}.when", check["when"], WHEN_CHOICES)

    if "scope" in check:
        validate_choice(f"{table_name}.scope", check["scope"], SCOPE_CHOICES)

    if "whitelist" in check:
        if check_name in UNSILENCEABLE_CHECKS:
            message = f"{table_name} has no whitelist - it never silences"
            raise ConfigurationError(message)

        _ = as_list(f"{table_name}.whitelist", check["whitelist"])

    if SOURCE_SETTING in check:
        validate_source_directories(check[SOURCE_SETTING])

    validate_number_option(check_name, check)

    for tool_name in TOOL_OPTIONS.get(check_name, frozenset()):
        if tool_name in check:
            _ = as_table(f"{table_name}.{tool_name}", check[tool_name])


def validate_python_environment(environment: object) -> None:
    if not isinstance(environment, str) or not environment:
        message = f"{ENVIRONMENT_SETTING} must be a folder path"
        raise ConfigurationError(message)


def validate_check_name(check_name: str) -> None:
    if check_name not in CHECK_ORDER:
        choices = ", ".join(CHECK_ORDER)
        message = f"checks: {check_name} is not one of {choices}"
        raise ConfigurationError(message)


def validate_checks(checks: object) -> None:
    checks_table = as_table(CHECKS_SETTING, checks)

    for check_name, check_section in checks_table.items():
        validate_check_name(check_name)
        validate_check(check_name, check_section)


def validate_configuration(
    configuration: Configuration, known_settings: set[str]
) -> None:
    if SOURCE_SETTING not in configuration:
        message = f"{SOURCE_SETTING} is required"
        raise ConfigurationError(message)

    validate_known_keys("checks.toml", configuration, known_settings)

    for setting_name, setting_value in configuration.items():
        validate_plain_values(setting_name, setting_value)

    validate_python_environment(configuration[ENVIRONMENT_SETTING])
    validate_source_directories(configuration[SOURCE_SETTING])
    validate_choice("stable", configuration["stable"], WHEN_CHOICES)

    validate_checks(configuration[CHECKS_SETTING])
