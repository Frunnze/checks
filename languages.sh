files_ending_in() {
    extensions=$1
    shift

    find -H "$@" -mindepth 1 \
        -name __pycache__ -prune -o \
        -name node_modules -prune -o \
        -type d \( -name '.?*' -o -name venv -o -name vendor \
        -o -name dist -o -name build \) \
        -exec git check-ignore -q {} \; -prune -o \
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

dart_files_in() {
    files_ending_in 'dart' "$@"
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

supported_languages="python typescript php dart"
unsupported_code_extensions="js jsx mjs cjs go rb java kt rs cs swift c cc \
cpp h hpp scala lua pl ex exs"

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
        echo "checks: $source_directory holds $unsupported_extensions" >&2
        echo "checks: files - no check supports that language, so" >&2
        echo "checks: they go unchecked" >&2
        echo "checks: (supported: $supported_languages)" >&2
    fi

    for language in $supported_languages; do
        if [ -n "$(directories_written_in "$language" "$source_directory")" ]
        then
            return
        fi
    done

    echo "checks: $source_directory holds no $supported_languages" >&2
    echo "checks: code, so no check can run on it" >&2
    exit 1
}
