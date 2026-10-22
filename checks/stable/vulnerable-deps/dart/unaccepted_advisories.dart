import 'dart:convert';
import 'dart:io';

typedef JsonObject = Map<String, Object?>;

List<String> unacceptedIn(
  JsonObject affectedPackage,
  List<String> acceptedAdvisories,
) {
  final package = affectedPackage['package']! as JsonObject;
  final packageName = package['name']! as String;
  final vulnerabilities = affectedPackage['vulnerabilities']! as List<Object?>;
  final findings = <String>[];

  for (final vulnerability in vulnerabilities) {
    final advisory = vulnerability! as JsonObject;
    final advisoryId = advisory['id']! as String;
    final aliases = advisory['aliases'] as List<Object?>? ?? const [];
    final identifiers = {advisoryId, ...aliases.cast<String>()};

    if (identifiers.any(acceptedAdvisories.contains)) {
      continue;
    }

    final summary = advisory['summary'] as String? ?? '';
    findings.add('$packageName: $advisoryId $summary');
  }

  return findings;
}

Future<void> main(List<String> acceptedAdvisories) async {
  final reportText = await utf8.decodeStream(stdin);
  final report = jsonDecode(reportText) as JsonObject;
  final results = report['results']! as List<Object?>;
  final unaccepted = <String>{};

  for (final result in results) {
    final packages = (result! as JsonObject)['packages']! as List<Object?>;

    for (final affectedPackage in packages) {
      final findings = unacceptedIn(
        affectedPackage! as JsonObject,
        acceptedAdvisories,
      );
      unaccepted.addAll(findings);
    }
  }

  final sortedFindings = unaccepted.toList()..sort();

  for (final finding in sortedFindings) {
    stdout.writeln(finding);
  }
}
