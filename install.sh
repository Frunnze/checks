#!/bin/sh
set -e
unset CDPATH

toolkit=$(cd "$(dirname "$0")" && pwd)
virtual_environment="$toolkit/.venv"
dart_tool_cache="$toolkit/.pub-cache"
property_test_finder="$toolkit/checks/experimental/property-tests/dart"
dart_code_linter_version=4.4.2
dependency_validator_version=5.1.0
toolkit_folder=$(basename "$toolkit")

if [ ! -d "$virtual_environment" ]; then
    python3 -m venv "$virtual_environment"
fi

"$virtual_environment/bin/pip" install --quiet --upgrade pip
"$virtual_environment/bin/pip" install --quiet -r "$toolkit/requirements.txt"

npm install --silent --prefix "$toolkit"

if command -v composer > /dev/null 2>&1; then
    composer install --quiet --working-dir="$toolkit"
else
    echo "install: composer is missing - php checks will not run"
fi

if command -v dart > /dev/null 2>&1; then
    rm -f "$dart_tool_cache/bin/property_test_coverage"
    PUB_CACHE="$dart_tool_cache" dart pub global activate \
        dart_code_linter "$dart_code_linter_version" > /dev/null
    PUB_CACHE="$dart_tool_cache" dart pub global activate \
        dependency_validator "$dependency_validator_version" > /dev/null
    PUB_CACHE="$dart_tool_cache" dart pub get \
        --directory "$property_test_finder" > /dev/null
    dart compile exe "$property_test_finder/property_test_coverage.dart" \
        -o "$dart_tool_cache/bin/property_test_coverage" > /dev/null
else
    echo "install: dart is missing - dart checks will not run"
fi

if ! command -v osv-scanner > /dev/null 2>&1; then
    echo "install: osv-scanner is missing - brew install osv-scanner"
fi

if ! command -v gitleaks > /dev/null 2>&1; then
    echo "install: gitleaks is missing - brew install gitleaks"
fi

project_root=$(git -C "$toolkit/.." rev-parse --show-toplevel 2> /dev/null \
    || true)

if [ -z "$project_root" ]; then
    echo "install: ready"
    exit 0
fi

git -C "$project_root" config core.hooksPath "$toolkit/hooks"

ignore_file="$project_root/.gitignore"

if ! grep -qx "$toolkit_folder/" "$ignore_file" 2> /dev/null; then
    if [ -s "$ignore_file" ] && [ -n "$(tail -c 1 "$ignore_file")" ]; then
        echo >> "$ignore_file"
    fi

    echo "$toolkit_folder/" >> "$ignore_file"
fi

echo "install: ready - the hooks of $project_root run $toolkit_folder"
