#!/bin/sh
set -e

toolkit=$(cd "$(dirname "$0")" && pwd)
virtual_environment="$toolkit/.venv"
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

if ! command -v gitleaks > /dev/null 2>&1; then
    echo "install: gitleaks is missing - brew install gitleaks"
fi

project_root=$(git -C "$toolkit/.." rev-parse --show-toplevel 2> /dev/null \
    || true)

if [ -z "$project_root" ]; then
    echo "install: ready"
    exit 0
fi

git -C "$project_root" config core.hooksPath "$toolkit_folder/hooks"

if ! grep -qx "$toolkit_folder/" "$project_root/.gitignore" 2> /dev/null
then
    echo "$toolkit_folder/" >> "$project_root/.gitignore"
fi

echo "install: ready - the hooks of $project_root run $toolkit_folder"
