feature_trees() {
    for source_directory in "$@"; do
        if ! is_tests_folder "$source_directory"; then
            echo "$source_directory"
        fi
    done
}

require_feature_layout() {
    features_folder=$1
    shift

    for source_directory in "$@"; do
        features="$source_directory/$features_folder"

        if [ ! -d "$features" ]; then
            echo "checks: $source_directory has no $features_folder" >&2
            echo "checks: folder - feature isolation needs" >&2
            echo "checks: $features/<feature>/ for each feature" >&2
            echo "checks: and an optional shared folder beside it" >&2
            exit 1
        fi

        loose_files=$(find "$features" -maxdepth 1 -type f \
            ! -name '__init__.py' ! -name '.*')

        fail_on_findings "$loose_files" \
            "every file in $features must live in a feature folder:"
    done
}
