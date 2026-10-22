cd "$project_root"

. "$toolkit/languages.sh"

export PYTHONIOENCODING=utf-8:surrogateescape

toolkit_python="$toolkit/.venv/bin/python"
python_tools="$toolkit/.venv/bin"
node_tools="$toolkit/node_modules/.bin"
php_tools="$toolkit/vendor/bin"
typescript_module="$toolkit/node_modules/typescript"
dart_tool_cache="$toolkit/.pub-cache"
dart_tools="$dart_tool_cache/bin"
node_binary=$(command -v node || true)
php_binary=$(command -v php || true)
composer_binary=$(command -v composer || true)
dart_binary=$(command -v dart || true)

require_binary() {
    if [ ! -x "$1" ]; then
        echo "checks: $2 is not installed -" >&2
        echo "checks: run ./install.sh in $toolkit" >&2
        exit 1
    fi
}

require_command() {
    if ! command -v "$1" > /dev/null 2>&1; then
        echo "checks: $1 is not installed - $2" >&2
        exit 1
    fi
}

require_node_modules() {
    if [ ! -d "$1/node_modules" ]; then
        echo "checks: $1 has no node_modules - run npm install there" >&2
        exit 1
    fi
}

require_resolved_dart_package() {
    if [ ! -f "$1/.dart_tool/package_config.json" ]; then
        echo "checks: $1 has no .dart_tool - run dart pub get there" >&2
        exit 1
    fi
}

require_strict_dart_rules() {
    strict_rules_package=package:very_good_analysis/

    if ! grep -qs "^[^#]*$strict_rules_package" \
        "$1/analysis_options.yaml"; then
        echo "checks: $1/analysis_options.yaml must include" >&2
        echo "checks: ${strict_rules_package}analysis_options.yaml" >&2
        exit 1
    fi
}

setting() {
    "$toolkit_python" "$toolkit/configuration/settings.py" \
        "$configuration_file" "$1"
}

whitelist_entries() {
    setting "checks.$check_name.whitelist"
}

whitelisted_rules_for() {
    whitelist_entries | sed -n "s/^$1://p"
}

without_whitelisted() {
    whitelisted=$(whitelist_entries)

    if [ -z "$whitelisted" ]; then
        cat
        return
    fi

    grep -a -v -x -F -e "$whitelisted" || true
}

within_scope() {
    if [ "$check_scope" != changed ]; then
        cat
        return
    fi

    awk '
        BEGIN {
            while ((getline path < ENVIRON["changed_files_list"]) > 0) {
                changed[++count] = path
            }
        }
        {
            for (position = 1; position <= count; position++) {
                path = changed[position]
                after_path = substr($0, length(path) + 1, 1)

                if (path == "" || index($0, path) != 1) {
                    continue
                }

                if (after_path == ":" || after_path == " ") {
                    print
                    next
                }
            }
        }
    '
}

reportable_findings() {
    without_whitelisted | within_scope
}

changed_files_under() {
    package=$(package_of "$1")
    owned_files=$(package_root_files "$package")

    awk -v source="$1/" -v tests="$(tests_of "$1")/" \
        -v package="$package/" -v owned_files="$owned_files" '
        BEGIN {
            count = split(owned_files, names, "\n")

            for (position = 1; position <= count; position++) {
                owned[names[position]] = 1
            }
        }
        {
            in_package = package == "./" || index($0, package) == 1
            name = package == "./" ? $0 : substr($0, length(package) + 1)
        }
        source == "./" || index($0, source) == 1 || index($0, tests) == 1 ||
        ($0 in owned) || (in_package && index(name, "/") == 0)
    ' "$changed_files_list"
}

directories_with_changes() {
    for source_directory in "$@"; do
        if [ -n "$(changed_files_under "$source_directory")" ]; then
            echo "$source_directory"
        fi
    done
}

changed_files_at() {
    if [ "$1" != pre-push ]; then
        git -c core.quotePath=false diff --cached --name-only \
            --no-renames --diff-filter=ACMD
        return
    fi

    if git rev-parse --verify --quiet "@{upstream}" > /dev/null; then
        git -c core.quotePath=false diff --name-only --no-renames \
            --diff-filter=ACMD "@{upstream}...HEAD"
        return
    fi

    echo "checks: the branch has no upstream yet, so every tracked" >&2
    echo "checks: file counts as changed" >&2
    git -c core.quotePath=false ls-files
}

fail_on_findings() {
    findings=$1
    shift

    if [ -z "$(printf '%s' "$findings" | tr -d '\n ')" ]; then
        return
    fi

    for explanation in "$@"; do
        echo "checks: $explanation" >&2
    done

    printf '%s\n' "$findings" | grep -a . >&2
    exit 1
}

existing_directories() {
    for directory in "$@"; do
        if [ -d "$directory" ]; then
            echo "$directory"
        fi
    done
}

package_of() {
    dirname "$1"
}

packages_of() {
    for source_directory in "$@"; do
        package_of "$source_directory"
    done | sort -u
}

package_folders() {
    wanted_package=$1
    shift

    for source_directory in "$@"; do
        if [ "$(package_of "$source_directory")" = "$wanted_package" ]; then
            echo "$source_directory"
        fi
    done
}

package_root_files() {
    "$toolkit_python" "$toolkit/configuration/root_files.py" \
        "$1" "$project_root"
}

tests_folder_name_of() {
    if [ -f "$1/pubspec.yaml" ] && [ -d "$1/test" ] && [ ! -d "$1/tests" ]
    then
        echo test
        return
    fi

    echo tests
}

tests_of() {
    package=$(package_of "$1")
    tests_folder_name=$(tests_folder_name_of "$package")

    if [ "$package" = . ]; then
        echo "$tests_folder_name"
        return
    fi

    echo "$package/$tests_folder_name"
}

is_flutter_package() {
    grep -qsE '^[[:space:]]+sdk:[[:space:]]*flutter[[:space:]]*$' \
        "$1/pubspec.yaml"
}

sources_and_tests() {
    for source_directory in "$@"; do
        echo "$source_directory"
        existing_directories "$(tests_of "$source_directory")"
    done
}

is_tests_folder() {
    [ "$(tests_of "$1")" = "$1" ]
}

require_listed_tests() {
    listed_tests=$(tests_of "$1")

    if ! setting "checks.$check_name.source_directories" \
        | grep -qxF -e "$listed_tests"; then
        echo "checks: $check_name needs $listed_tests, the tests of" >&2
        echo "checks: $1 - add it to source_directories" >&2
        exit 1
    fi
}

tested_sources() {
    for source_directory in "$@"; do
        if is_tests_folder "$source_directory"; then
            continue
        fi

        require_listed_tests "$source_directory"
        echo "$source_directory"
    done
}

project_python() {
    echo "$project_root/$(setting python_environment)/bin/python"
}

installed_python_packages() {
    python_binary=$(project_python)
    require_binary "$python_binary" "the project python ($python_binary)"

    "$python_binary" -c \
        'import sysconfig; print(sysconfig.get_paths()["purelib"])'
}

unreachable_registry="ENOTFOUND|EAI_AGAIN|ETIMEDOUT|ECONNREFUSED\
|ECONNRESET|ERR_SOCKET_TIMEOUT|Could not resolve host|curl error\
|requests\.exceptions\.(ConnectionError|ConnectTimeout|ReadTimeout|Timeout\
|ProxyError|SSLError)|no such host|connection refused|i/o timeout"

package_dockerfiles() {
    for source_directory in "$@"; do
        find "$(package_of "$source_directory")" -maxdepth 1 -type f \
            -iname 'Dockerfile*'
    done
}

generated_configuration() {
    "$toolkit_python" "$toolkit/configuration/tool_configurations.py" \
        "$configuration_file" "$1" "$2" "$project_root"
}
