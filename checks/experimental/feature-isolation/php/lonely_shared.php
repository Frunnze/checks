<?php

declare(strict_types=1);

require __DIR__ . '/module_references.php';

const MINIMUM_OWNING_FEATURES = 2;

$owners_of     = array();
$shared_edges  = array();
$feature_edges = array();

foreach ( paths_from_standard_input() as $file_path ) {
	if ( is_shared( $file_path ) ) {
		$owners_of[ $file_path ] = array();
	}

	foreach ( referenced_modules_in( $file_path ) as $reference ) {
		if ( ! is_shared( $reference['module'] ) ) {
			continue;
		}

		$feature = feature_of( $file_path );

		if ( null !== $feature ) {
			$feature_edges[] = array( $feature, $reference['module'] );
		} elseif ( is_shared( $file_path ) ) {
			$shared_edges[] = array( $file_path, $reference['module'] );
		}
	}
}

foreach ( $feature_edges as list( $feature, $module ) ) {
	$owners_of[ $module ][ $feature ] = true;
}

do {
	$is_changed = false;

	foreach ( $shared_edges as list( $user, $module ) ) {
		$module_owners        = $owners_of[ $module ] ?? array();
		$user_owners          = $owners_of[ $user ] ?? array();
		$owners_of[ $module ] = $module_owners + $user_owners;
		$is_changed           = $is_changed
			|| count( $owners_of[ $module ] ) !== count( $module_owners );
	}
} while ( $is_changed );

ksort( $owners_of );

foreach ( $owners_of as $module => $owners ) {
	if ( count( $owners ) >= MINIMUM_OWNING_FEATURES ) {
		continue;
	}

	$reason = array() === $owners
		? 'no feature uses it'
		: 'only ' . array_key_first( $owners ) . ' uses it';

	echo $module, ': ', $reason, "\n";
}
