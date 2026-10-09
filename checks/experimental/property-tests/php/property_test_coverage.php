<?php

declare(strict_types=1);

require __DIR__ . '/definitions.php';

$source_directory = $argv[1] ?? '';
$property_tests   = array();
$problems         = array();
$source_files     = array();

foreach ( paths_from_standard_input() as $file_path ) {
	if ( ! str_starts_with( $file_path, $source_directory . '/' ) ) {
		foreach ( definitions_in( $file_path ) as $definition ) {
			if ( ! str_starts_with( $definition['name'], TEST_PREFIX ) ) {
				continue;
			}

			if ( ! in_array( PROPERTY_CALL, $definition['body'], true ) ) {
				$problems[] = $file_path . ':' . $definition['line'] . ': '
					. $definition['name'] . ' is not a property test - '
					. 'generate its input with $this->forAll()';
				continue;
			}

			$property_tests[] = $definition['name'];
		}

		continue;
	}

	$source_files[] = $file_path;
}

foreach ( $source_files as $file_path ) {
	foreach ( definitions_in( $file_path ) as $definition ) {
		if ( array() === $definition['body'] ) {
			continue;
		}

		if ( str_starts_with( $definition['name'], MAGIC_PREFIX ) ) {
			continue;
		}

		$expected = TEST_PREFIX . $definition['name'] . PROPERTY_MARKER;
		$covered  = array_filter(
			$property_tests,
			static fn( string $test ): bool => str_starts_with(
				$test,
				$expected
			)
		);

		if ( array() === $covered ) {
			$problems[] = $file_path . ':' . $definition['line'] . ': '
				. $definition['name'] . ' needs a property test named '
				. $expected . '<what it guarantees>';
		}
	}
}

sort( $problems );
echo implode( "\n", $problems ), "\n";
