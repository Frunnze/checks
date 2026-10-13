from pathlib import Path

from check_support import (
    WORDPRESS_MANIFEST,
    php_package,
    run_configured,
    stage_file,
)

PLUGIN_CONFIGURATION = 'source_directories = ["api/src", "api/tests"]\n'
CLOCK = "<?php\ninterface Clock {\n    public function now(): int;\n}\n"
GREETER = (
    "<?php\nfinal class Greeter {\n"
    "    public function __construct(private Clock $clock) {}\n"
    "    public function greet(): int {\n"
    "        return $this->clock->now();\n    }\n}\n"
)
SYSTEM_CLOCK = (
    "<?php\nfinal class SystemClock implements Clock {\n"
    "    public function now(): int {\n        return time();\n    }\n}\n"
)
FIXED_CLOCK = (
    "<?php\nfinal class FixedClock implements Clock {\n"
    "    public function now(): int {\n        return 1;\n    }\n}\n"
)
PLUGIN_ENTRY = "<?php\n(new Greeter(new SystemClock()))->greet();\n"
UNCALLED_METHOD = (
    "<?php\nfinal class Unreached {\n"
    "    public function forgotten(): int {\n        return 2;\n    }\n}\n"
)


def _plugin(tmp_path: Path) -> None:
    php_package(tmp_path, "api", WORDPRESS_MANIFEST)
    stage_file(tmp_path, "api/src/Clock.php", CLOCK)
    stage_file(tmp_path, "api/src/Greeter.php", GREETER)
    stage_file(tmp_path, "api/src/SystemClock.php", SYSTEM_CLOCK)
    stage_file(tmp_path, "api/tests/FixedClock.php", FIXED_CLOCK)
    stage_file(tmp_path, "plugin.php", PLUGIN_ENTRY)


def test_passes_on_code_reached_from_the_plugin_file_and_from_src(
    tmp_path: Path,
) -> None:
    _plugin(tmp_path)

    finished = run_configured(tmp_path, PLUGIN_CONFIGURATION, "dead-code")

    assert finished.returncode == 0, finished.stdout + finished.stderr


def test_fails_on_a_method_nothing_calls(tmp_path: Path) -> None:
    _plugin(tmp_path)
    stage_file(tmp_path, "api/src/Unreached.php", UNCALLED_METHOD)

    finished = run_configured(tmp_path, PLUGIN_CONFIGURATION, "dead-code")

    assert finished.returncode == 1
    assert "Unreached::forgotten" in finished.stdout
