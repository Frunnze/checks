import json
import subprocess
from pathlib import Path
from xml.etree import ElementTree

from configuration_support import written_configuration
from tool_configurations import eslint_configuration, generated_configuration

PACKAGE = Path("/project/ui")
SOURCE_CONFIGURATION = 'source_directories = ["src"]\n'
PRESETS_MODULE_TEXT = (
    "export const presets = {};\n"
    "export function typescriptConfigFor() {\n"
    '  return [{ name: "base" }];\n'
    "}\n"
)


def _manifest(package: Path, manifest: dict[str, object]) -> None:
    _ = (package / "composer.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def _generated(package: Path, settings: str, tool_name: str) -> str:
    configuration = written_configuration(
        package, SOURCE_CONFIGURATION + settings
    )

    return generated_configuration(configuration, tool_name, (package, package))


def test_phpstan_keeps_the_wordpress_extension_beside_written_includes(
    tmp_path: Path,
) -> None:
    _manifest(tmp_path, {"type": "wordpress-plugin"})

    generated = _generated(
        tmp_path,
        '[checks.strict-typing.phpstan]\nincludes = ["baseline.neon"]\n',
        "phpstan",
    )

    includes = json.loads(generated)["includes"]
    assert includes[1].endswith("phpstan-wordpress/extension.neon")
    assert includes[2] == str(tmp_path / "baseline.neon")


def test_phpcs_keeps_the_wordpress_excludes_beside_written_ones(
    tmp_path: Path,
) -> None:
    _manifest(tmp_path, {"type": "wordpress-plugin"})

    generated = _generated(
        tmp_path,
        '[checks.linters.phpcs]\nexclude = ["WordPress.PHP.YodaConditions"]\n',
        "phpcs",
    )

    ruleset = ElementTree.fromstring(generated)
    excluded = [element.get("name") for element in ruleset.iter("exclude")]
    assert "WordPress.Files.FileName" in excluded
    assert "WordPress.PHP.YodaConditions" in excluded


def test_phpstan_never_targets_a_php_version_it_cannot_analyse(
    tmp_path: Path,
) -> None:
    _manifest(tmp_path, {"require": {"php": ">=5.6"}})

    generated = _generated(tmp_path, "", "phpstan")

    assert json.loads(generated)["parameters"]["phpVersion"] == 70100


def test_eslint_configuration_loads_from_a_folder_with_url_characters(
    tmp_path: Path,
) -> None:
    toolkit = tmp_path / "C# 100%?"
    toolkit.mkdir()
    presets_module = toolkit / "eslint-presets.mjs"
    _ = presets_module.write_text(PRESETS_MODULE_TEXT, encoding="utf-8")
    configuration_path = tmp_path / "eslint.config.mjs"
    _ = configuration_path.write_text(
        eslint_configuration({}, presets_module, PACKAGE), encoding="utf-8"
    )
    loading_script = (
        f"const loaded = await import({json.dumps(configuration_path.as_uri())});"
        "process.stdout.write(JSON.stringify(loaded.default));"
    )

    loaded = subprocess.run(
        ["node", "--input-type=module", "--eval", loading_script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert json.loads(loaded.stdout) == [
        {"name": "base", "basePath": str(PACKAGE)}
    ]
