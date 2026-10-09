<?php

declare(strict_types=1);

require __DIR__ . '/module_references.php';

$crossings = array();

foreach ( paths_from_standard_input() as $file_path ) {
	$importing_feature = feature_of( $file_path );

	if ( null === $importing_feature ) {
		continue;
	}

	foreach ( referenced_modules_in( $file_path ) as $reference ) {
		$imported_feature = feature_of( $reference['module'] );

		if ( null === $imported_feature ) {
			continue;
		}

		if ( $imported_feature === $importing_feature ) {
			continue;
		}

		$crossings[] = $file_path . ':' . $reference['line'] . ': '
			. $reference['module'];
	}
}

sort( $crossings );
echo implode( "\n", array_unique( $crossings ) ), "\n";
