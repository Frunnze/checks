import json
from pathlib import Path
from xml.etree import ElementTree

import pytest
from hypothesis import given
from hypothesis import strategies as st

from settings_validation import ConfigurationError
from dependency_analyser_settings import dependency_analyser_configuration
from phpstan_settings import php_version_of, phpstan_configuration
from tool_configurations import eslint_configuration, phpcs_configuration

PACKAGE = Path("/project/api")
DEFAULT_NEON = Path("/toolkit/phpstan.neon")
BASE_RULESET = Path("/toolkit/phpcs-base.xml")
PRESETS_MODULE = Path("/toolkit/eslint-presets.mjs")

rule_names = st.text(alphabet="abcdefghijklmnopqrstuvwxyz-/", min_size=1)
sniff_names = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ.", min_size=1)


def _exported_configs(module_text: str) -> list[object]:
    json_part = module_text.split("const userConfigs = ", 1)[1]
    json_text = json_part.split(";\n", 1)[0]

    return json.loads(json_text)


def test_phpstan_always_includes_the_toolkit_defaults_first() -> None:
    neon_text = phpstan_configuration(
        {"includes": ["vendor/extension.neon"]}, DEFAULT_NEON, PACKAGE, {}
    )

    generated = json.loads(neon_text)

    assert generated["includes"] == [
        str(DEFAULT_NEON),
        str(PACKAGE / "vendor/extension.neon"),
    ]


def test_phpstan_passes_parameters_through_unchanged() -> None:
    neon_text = phpstan_configuration(
        {"parameters": {"level": 8}}, DEFAULT_NEON, PACKAGE, {}
    )

    assert json.loads(neon_text)["parameters"] == {"level": 8}


def test_phpcs_uses_psr12_when_no_standard_is_named() -> None:
    ruleset = ElementTree.fromstring(phpcs_configuration({}, BASE_RULESET))

    references = [rule.get("ref") for rule in ruleset.iter("rule")]

    assert references[:2] == ["PSR12", str(BASE_RULESET)]


def test_phpcs_writes_array_properties_as_elements() -> None:
    ruleset = ElementTree.fromstring(
        phpcs_configuration(
            {
                "standard": "WordPress-Extra",
                "properties": {
                    "WordPress.NamingConventions.PrefixAllGlobals": {
                        "prefixes": ["link_checkup", "LinkCheckup"],
                    },
                },
            },
            BASE_RULESET,
        )
    )

    elements = [element.get("value") for element in ruleset.iter("element")]

    assert elements == ["link_checkup", "LinkCheckup"]


def test_phpcs_rejects_an_unknown_setting() -> None:
    with pytest.raises(ConfigurationError, match="standards"):
        _ = phpcs_configuration({"standards": ["PSR12"]}, BASE_RULESET)


def test_eslint_rejects_an_unknown_preset() -> None:
    with pytest.raises(ConfigurationError, match="vue"):
        _ = eslint_configuration({"presets": ["vue"]}, PRESETS_MODULE, PACKAGE)


def test_eslint_scopes_every_user_config_to_the_package() -> None:
    module_text = eslint_configuration(
        {
            "rules": {"no-console": "error"},
            "overrides": [
                {"files": ["src/a.tsx"], "rules": {"no-alert": "off"}},
            ],
        },
        PRESETS_MODULE,
        PACKAGE,
    )

    configs = _exported_configs(module_text)

    assert configs == [
        {"basePath": str(PACKAGE), "rules": {"no-console": "error"}},
        {
            "basePath": str(PACKAGE),
            "files": ["src/a.tsx"],
            "rules": {"no-alert": "off"},
        },
    ]


@given(
    st.dictionaries(rule_names, st.sampled_from(["off", "warn"]), min_size=1)
)
def test_eslint_configuration_property_keeps_every_rule(
    rules: dict[str, str],
) -> None:
    module_text = eslint_configuration(
        {"rules": rules}, PRESETS_MODULE, PACKAGE
    )

    configs = _exported_configs(module_text)

    assert configs[0] == {"basePath": str(PACKAGE), "rules": rules}


@given(st.lists(sniff_names, max_size=5))
def test_phpcs_configuration_property_excludes_every_named_sniff(
    excluded_sniffs: list[str],
) -> None:
    ruleset = ElementTree.fromstring(
        phpcs_configuration({"exclude": excluded_sniffs}, BASE_RULESET)
    )

    excluded = [element.get("name") for element in ruleset.iter("exclude")]

    assert excluded == excluded_sniffs


@given(st.lists(st.text(alphabet="abcdefgh/._", min_size=1), max_size=4))
def test_phpstan_configuration_property_resolves_includes_in_the_package(
    includes: list[str],
) -> None:
    neon_text = phpstan_configuration(
        {"includes": includes}, DEFAULT_NEON, PACKAGE, {}
    )

    generated_includes = json.loads(neon_text)["includes"]

    assert generated_includes[0] == str(DEFAULT_NEON)
    assert len(generated_includes) == len(includes) + 1


def test_phpcs_limits_a_sniff_with_exclude_patterns() -> None:
    ruleset = ElementTree.fromstring(
        phpcs_configuration(
            {"exclude-patterns": {"WordPress.DB.DirectDatabaseQuery": ["tests/*"]}},
            BASE_RULESET,
        )
    )

    sniff_rules = [
        rule
        for rule in ruleset.iter("rule")
        if rule.get("ref") == "WordPress.DB.DirectDatabaseQuery"
    ]
    patterns = [element.text for element in sniff_rules[0].iter("exclude-pattern")]

    assert patterns == ["tests/*"]


def test_dependency_analyser_ignores_the_named_error_types() -> None:
    php_text = dependency_analyser_configuration(
        {"ignore-errors": ["UNKNOWN_CLASS"]}
    )

    assert "ignoreErrors([ErrorType::UNKNOWN_CLASS])" in php_text


def test_dependency_analyser_rejects_an_unknown_error_type() -> None:
    with pytest.raises(ConfigurationError, match="UNKNOWN_THING"):
        _ = dependency_analyser_configuration(
            {"ignore-errors": ["UNKNOWN_THING"]}
        )


@given(
    st.lists(
        st.sampled_from(["UNKNOWN_CLASS", "UNKNOWN_FUNCTION", "DEV_DEPENDENCY_IN_PROD"]),
        unique=True,
    )
)
def test_dependency_analyser_configuration_property_names_every_error_type(
    error_types: list[str],
) -> None:
    php_text = dependency_analyser_configuration({"ignore-errors": error_types})

    for error_type in error_types:
        assert f"ErrorType::{error_type}" in php_text


def test_phpstan_lets_written_parameters_win_over_derived_ones() -> None:
    neon_text = phpstan_configuration(
        {"parameters": {"phpVersion": 80300}},
        DEFAULT_NEON,
        PACKAGE,
        {"phpVersion": 80100, "scanFiles": ["/project/plugin.php"]},
    )

    parameters = json.loads(neon_text)["parameters"]

    assert parameters == {
        "phpVersion": 80300,
        "scanFiles": ["/project/plugin.php"],
    }


@pytest.mark.parametrize(
    ("requirement", "php_version"),
    [
        ("^7.4 || ^8.1", 70400),
        ("^8.1 || ^7.4", 70400),
        ("<8.0 >=7.2", 70200),
        ("~8.2.0", 80200),
    ],
)
def test_php_version_is_the_lowest_one_the_requirement_allows(
    tmp_path: Path, requirement: str, php_version: int
) -> None:
    manifest = {"require": {"php": requirement}}
    _ = (tmp_path / "composer.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    assert php_version_of(tmp_path) == php_version


def test_eslint_rejects_a_preset_that_is_not_a_name() -> None:
    with pytest.raises(ConfigurationError, match="presets"):
        _ = eslint_configuration({"presets": [[]]}, PRESETS_MODULE, PACKAGE)


def test_dependency_analyser_rejects_an_error_type_that_is_not_a_name(
) -> None:
    with pytest.raises(ConfigurationError, match="ignore-errors"):
        _ = dependency_analyser_configuration({"ignore-errors": [{}]})


def test_phpcs_rejects_a_standard_that_is_not_a_name() -> None:
    with pytest.raises(ConfigurationError, match="standard"):
        _ = phpcs_configuration(
            {"standard": ["PSR12", "PSR2"]}, BASE_RULESET
        )
