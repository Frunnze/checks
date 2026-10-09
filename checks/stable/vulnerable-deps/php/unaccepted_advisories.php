<?php

declare(strict_types=1);

$accepted_advisories = array_slice($argv, 1);
$audit_report = json_decode(
    (string) stream_get_contents(STDIN),
    true,
    512,
    JSON_THROW_ON_ERROR
);
$unaccepted = [];

foreach ($audit_report['advisories'] ?? [] as $package => $advisories) {
    foreach ($advisories as $advisory) {
        $identifiers = [$advisory['advisoryId'], $advisory['cve'] ?? ''];

        if (array_intersect($identifiers, $accepted_advisories) !== []) {
            continue;
        }

        $unaccepted[] = $package . ': ' . $advisory['advisoryId']
            . ' ' . $advisory['title'];
    }
}

sort($unaccepted);
echo implode("\n", $unaccepted), "\n";
