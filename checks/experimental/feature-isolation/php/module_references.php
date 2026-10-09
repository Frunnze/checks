<?php

declare(strict_types=1);

const FEATURES_FOLDER  = 'Features';
const SHARED_FOLDER    = 'Shared';
const AUTOLOAD_SECTION = 'psr-4';

define( 'SOURCE_DIRECTORY', rtrim( $argv[1] ?? '', '/' ) );
define( 'ROOT_NAMESPACE', root_namespace_of( SOURCE_DIRECTORY ) );

function root_namespace_of( string $source_directory ): string {
	$manifest_path = dirname( $source_directory ) . '/composer.json';
	$manifest      = json_decode(
		(string) file_get_contents( $manifest_path ),
		true,
		512,
		JSON_THROW_ON_ERROR
	);
	$autoload      = $manifest['autoload'][ AUTOLOAD_SECTION ] ?? array();

	foreach ( $autoload as $namespace => $directory ) {
		if ( 'src' === rtrim( (string) $directory, '/' ) ) {
			return (string) $namespace;
		}
	}

	fwrite( STDERR, "$manifest_path maps no namespace to src/\n" );
	exit( 1 );
}

/** @return list<array{module: string, line: int}> */
function referenced_modules_in( string $file_path ): array {
	$source        = (string) file_get_contents( $file_path );
	$known_modules = modules_on_disk();
	$namespace     = '';
	$found         = array();

	foreach ( token_get_all( $source ) as $token ) {
		if ( ! is_array( $token ) ) {
			continue;
		}

		if ( T_NAMESPACE === $token[0] ) {
			$namespace = namespace_declared_in( $source );
		}

		$module = module_of_token( $token, $namespace, $known_modules );

		if ( null !== $module && $module !== $file_path ) {
			$found[] = array(
				'module' => $module,
				'line'   => $token[2],
			);
		}
	}

	return $found;
}

/**
 * @param array{0: int, 1: string, 2: int} $token
 * @param array<string, true>              $known_modules
 */
function module_of_token(
	array $token,
	string $current_namespace,
	array $known_modules
): string|null {
	if ( T_STRING === $token[0] && '' !== $current_namespace ) {
		$qualified_name = $current_namespace . '\\' . $token[1];

		return module_named( $qualified_name, $known_modules );
	}

	return module_named( ltrim( $token[1], '\\' ), $known_modules );
}

function namespace_declared_in( string $source ): string {
	$matches = array();

	preg_match( '/^namespace\s+([\w\\\\]+);/m', $source, $matches );

	return $matches[1] ?? '';
}

/** @param array<string, true> $known_modules */
function module_named(
	string $qualified_name,
	array $known_modules
): string|null {
	if ( ! str_starts_with( $qualified_name, ROOT_NAMESPACE ) ) {
		return null;
	}

	$relative_name = substr( $qualified_name, strlen( ROOT_NAMESPACE ) );
	$module        = SOURCE_DIRECTORY . '/'
		. str_replace( '\\', '/', $relative_name ) . '.php';

	return isset( $known_modules[ $module ] ) ? $module : null;
}

/** @return array<string, true> */
function modules_on_disk(): array {
	$modules = array();
	$files   = new RecursiveIteratorIterator(
		new RecursiveDirectoryIterator( SOURCE_DIRECTORY )
	);

	foreach ( $files as $file ) {
		if ( $file instanceof SplFileInfo && $file->isFile() ) {
			$modules[ $file->getPathname() ] = true;
		}
	}

	return $modules;
}

function top_folder_of( string $file_path, string $folder ): string|null {
	$prefix = SOURCE_DIRECTORY . '/' . $folder . '/';

	if ( ! str_starts_with( $file_path, $prefix ) ) {
		return null;
	}

	$segments = explode( '/', substr( $file_path, strlen( $prefix ) ) );

	return count( $segments ) > 1 ? $segments[0] : null;
}

function feature_of( string $file_path ): string|null {
	return top_folder_of( $file_path, FEATURES_FOLDER );
}

function is_shared( string $file_path ): bool {
	$prefix = SOURCE_DIRECTORY . '/' . SHARED_FOLDER . '/';

	return str_starts_with( $file_path, $prefix );
}

/** @return list<string> */
function paths_from_standard_input(): array {
	$listing = (string) stream_get_contents( STDIN );
	$paths   = preg_split( '/\s+/', $listing, -1, PREG_SPLIT_NO_EMPTY );

	return false === $paths ? array() : $paths;
}
