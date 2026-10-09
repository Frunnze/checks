<?php

declare(strict_types=1);

const PROPERTY_CALL   = 'forAll';
const TEST_PREFIX     = 'test_';
const PROPERTY_MARKER = '_property_';
const MAGIC_PREFIX    = '__';

/** @return list<array{name: string, line: int, body: list<string>}> */
function definitions_in( string $file_path ): array {
	$tokens = token_get_all( (string) file_get_contents( $file_path ) );
	$found  = array();

	foreach ( $tokens as $index => $token ) {
		if ( ! is_array( $token ) || T_FUNCTION !== $token[0] ) {
			continue;
		}

		$name_index = next_meaningful_index( $tokens, $index );
		$name       = $tokens[ $name_index ] ?? null;

		if ( ! is_array( $name ) || T_STRING !== $name[0] ) {
			continue;
		}

		$found[] = array(
			'name' => $name[1],
			'line' => $name[2],
			'body' => body_after( $tokens, $name_index ),
		);
	}

	return $found;
}

/** @param list<array{0: int, 1: string, 2: int}|string> $tokens */
function next_meaningful_index( array $tokens, int $index ): int {
	$next = $index + 1;

	while ( is_whitespace_token( $tokens[ $next ] ?? null ) ) {
		++$next;
	}

	return $next;
}

/** @param array{0: int, 1: string, 2: int}|string|null $token */
function is_whitespace_token( array|string|null $token ): bool {
	return is_array( $token ) && T_WHITESPACE === $token[0];
}

/**
 * @param list<array{0: int, 1: string, 2: int}|string> $tokens
 * @return list<string>
 */
function body_after( array $tokens, int $index ): array {
	$depth = 0;
	$body  = array();

	foreach ( array_slice( $tokens, $index ) as $token ) {
		$text = is_array( $token ) ? $token[1] : $token;

		if ( 0 === $depth && ';' === $text ) {
			return array();
		}

		$depth += ( '{' === $text ? 1 : 0 ) - ( '}' === $text ? 1 : 0 );
		$body[] = $text;

		if ( '}' === $text && 0 === $depth ) {
			return $body;
		}
	}

	return $body;
}

/** @return list<string> */
function paths_from_standard_input(): array {
	$listing = (string) stream_get_contents( STDIN );
	$paths   = preg_split( '/\s+/', $listing, -1, PREG_SPLIT_NO_EMPTY );

	return false === $paths ? array() : $paths;
}
