cd "$project_root"

toolkit_python="$toolkit/.venv/bin/python"
python_tools="$toolkit/.venv/bin"
node_tools="$toolkit/node_modules/.bin"
php_tools="$toolkit/vendor/bin"
typescript_module="$toolkit/node_modules/typescript"
node_binary=$(command -v node || true)
php_binary=$(command -v php || true)
composer_binary=$(command -v composer || true)

require_binary() {
    if [ ! -x "$1" ]; then
        echo "pre-commit: $2 is not installed -" >&2
        echo "pre-commit: run ./install.sh in $toolkit" >&2
        exit 1
    fi
}

require_command() {
    if ! command -v "$1" > /dev/null 2>&1; then
        echo "pre-commit: $1 is not installed - $2" >&2
        exit 1
    fi
}

require_node_modules() {
    if [ ! -d "$1/node_modules" ]; then
        echo "pre-commit: $1 has no node_modules - run npm install there" >&2
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
        BEGIN { count = split(ENVIRON["changed_files"], changed, "\n") }
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
    printf '%s\n' "$changed_files" | awk \
        -v source="$1/" -v tests="$(tests_of "$1")/" \
        'index($0, source) == 1 || index($0, tests) == 1'
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
            --diff-filter=ACMR
        return
    fi

    if git rev-parse --verify --quiet "@{upstream}" > /dev/null; then
        git -c core.quotePath=false diff --name-only --diff-filter=ACMR \
            "@{upstream}...HEAD"
        return
    fi

    echo "pre-commit: the branch has no upstream yet, so every tracked" >&2
    echo "pre-commit: file counts as changed" >&2
    git -c core.quotePath=false ls-files
}

fail_on_findings() {
    findings=$1
    shift

    if [ -z "$(printf '%s' "$findings" | tr -d '\n ')" ]; then
        return
    fi

    for explanation in "$@"; do
        echo "pre-commit: $explanation" >&2
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

tests_of() {
    package=$(package_of "$1")

    if [ "$package" = . ]; then
        echo tests
        return
    fi

    echo "$package/tests"
}

sources_and_tests() {
    for source_directory in "$@"; do
        echo "$source_directory"
        existing_directories "$(tests_of "$source_directory")"
    done
}

files_ending_in() {
    extensions=$1
    shift

    find -H "$@" -mindepth 1 \
        -name __pycache__ -prune -o \
        -name node_modules -prune -o \
        -name vendor -prune -o \
        -name dist -prune -o \
        -name build -prune -o \
        -type f -print \
        | grep -a -E "\.($extensions)\$" \
        | sed 's|^\./||' \
        | sort -u
}

python_files_in() {
    files_ending_in 'py' "$@"
}

typescript_files_in() {
    files_ending_in 'ts|tsx|mts|cts' "$@"
}

php_files_in() {
    files_ending_in 'php' "$@"
}

directories_written_in() {
    language=$1
    shift

    for source_directory in "$@"; do
        first_file=$("${language}_files_in" "$source_directory" | head -n 1)

        if [ -n "$first_file" ]; then
            echo "$source_directory"
        fi
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
|ECONNRESET|ERR_SOCKET_TIMEOUT|network|Could not resolve host|curl error\
|requests\.exceptions\.(ConnectionError|ConnectTimeout|ReadTimeout|Timeout\
|ProxyError|SSLError)"

supported_languages="python typescript php"
unsupported_code_extensions="js jsx mjs cjs go rb java kt rs cs swift c cc \
cpp h hpp scala dart lua pl ex exs"

unsupported_extensions_in() {
    for extension in $unsupported_code_extensions; do
        first_file=$(find "$1" -name node_modules -prune -o \
            -type f -name "*.$extension" -print | head -n 1)

        if [ -n "$first_file" ]; then
            echo ".$extension"
        fi
    done
}

require_supported_language() {
    source_directory=$1
    unsupported_extensions=$(unsupported_extensions_in "$source_directory" \
        | paste -sd' ' -)

    if [ -n "$unsupported_extensions" ]; then
        echo "pre-commit: $source_directory holds $unsupported_extensions" >&2
        echo "pre-commit: files - no check supports that language, so" >&2
        echo "pre-commit: they go unchecked" >&2
        echo "pre-commit: (supported: $supported_languages)" >&2
    fi

    for language in $supported_languages; do
        if [ -n "$(directories_written_in "$language" "$source_directory")" ]
        then
            return
        fi
    done

    echo "pre-commit: $source_directory holds no $supported_languages" >&2
    echo "pre-commit: code, so no check can run on it" >&2
    exit 1
}

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

package_folders() {
    existing_directories "$(basename "$1")" tests
}
