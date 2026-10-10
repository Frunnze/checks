from settings_validation import (
    as_list,
    validate_choice,
    validate_known_keys,
)

ANALYSER_KEYS = {"ignore-errors"}
ANALYSER_ERROR_TYPES = frozenset({
    "UNKNOWN_CLASS",
    "UNKNOWN_FUNCTION",
    "SHADOW_DEPENDENCY",
    "UNUSED_DEPENDENCY",
    "DEV_DEPENDENCY_IN_PROD",
    "PROD_DEPENDENCY_ONLY_IN_DEV",
})
ANALYSER_MODULE = """<?php

use ShipMonk\\ComposerDependencyAnalyser\\Config\\Configuration;
use ShipMonk\\ComposerDependencyAnalyser\\Config\\ErrorType;

return (new Configuration())->ignoreErrors([{ignored_errors}]);
"""


def dependency_analyser_configuration(section: dict[str, object]) -> str:
    validate_known_keys("composer-dependency-analyser", section, ANALYSER_KEYS)
    ignored_errors: list[str] = []
    setting_name = "composer-dependency-analyser.ignore-errors"

    for error_type in as_list(setting_name, section.get("ignore-errors", [])):
        validate_choice(setting_name, error_type, ANALYSER_ERROR_TYPES)
        ignored_errors.append(f"ErrorType::{error_type}")

    return ANALYSER_MODULE.format(ignored_errors=", ".join(ignored_errors))
