import 'dart:convert';
import 'dart:io';

import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:path/path.dart' as path;

import 'definitions.dart';
import 'property_test_titles.dart';

const String testsDirectoryName = 'tests';
const String propertyMarker = ' property';
const int minimumPropertyTests = 4;

final class UntestedDefinition {
  const UntestedDefinition({
    required this.filePath,
    required this.lineNumber,
    required this.name,
  });

  final String filePath;
  final int lineNumber;
  final String name;

  String get report {
    final expectedTitle = '"$name$propertyMarker ..."';

    return '$filePath:$lineNumber: $name needs $minimumPropertyTests '
        'property tests titled $expectedTitle';
  }
}

CompilationUnit parsedFile(String filePath) {
  final content = File(filePath).readAsStringSync();

  return parseString(content: content, path: filePath).unit;
}

bool isWithin(String directory, String filePath) {
  return path.isWithin(path.normalize(directory), path.normalize(filePath));
}

bool isCovered(String name, Set<String> propertyTestTitles) {
  final expectedStart = '$name$propertyMarker';
  var matchingTestCount = 0;

  for (final title in propertyTestTitles) {
    if (title.startsWith(expectedStart)) {
      matchingTestCount += 1;
    }
  }

  return matchingTestCount >= minimumPropertyTests;
}

List<UntestedDefinition> untestedIn(
  String filePath,
  Set<String> propertyTestTitles,
) {
  final unit = parsedFile(filePath);
  final untested = <UntestedDefinition>[];

  for (final definition in definitionsIn(unit)) {
    if (isCovered(definition.name, propertyTestTitles)) {
      continue;
    }

    final location = unit.lineInfo.getLocation(definition.offset);
    untested.add(
      UntestedDefinition(
        filePath: filePath,
        lineNumber: location.lineNumber,
        name: definition.name,
      ),
    );
  }

  return untested;
}

int compareLocations(UntestedDefinition left, UntestedDefinition right) {
  final byPath = left.filePath.compareTo(right.filePath);

  if (byPath != 0) {
    return byPath;
  }

  final byLine = left.lineNumber.compareTo(right.lineNumber);

  if (byLine != 0) {
    return byLine;
  }

  return left.name.compareTo(right.name);
}

Future<void> main(List<String> arguments) async {
  final sourceDirectory = arguments.single;
  final testsDirectory = path.join(
    path.dirname(sourceDirectory),
    testsDirectoryName,
  );
  final listing = await utf8.decodeStream(stdin);
  final sourcePaths = <String>[];
  final propertyTestTitles = <String>{};

  for (final filePath in const LineSplitter().convert(listing)) {
    if (filePath.isEmpty) {
      continue;
    }

    if (isWithin(testsDirectory, filePath)) {
      propertyTestTitles.addAll(propertyTestTitlesIn(parsedFile(filePath)));
    } else if (isWithin(sourceDirectory, filePath)) {
      sourcePaths.add(filePath);
    }
  }

  final untested = <UntestedDefinition>[];

  for (final sourcePath in sourcePaths) {
    untested.addAll(untestedIn(sourcePath, propertyTestTitles));
  }

  untested.sort(compareLocations);

  for (final untestedDefinition in untested) {
    stdout.writeln(untestedDefinition.report);
  }
}
