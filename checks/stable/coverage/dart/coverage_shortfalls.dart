import 'dart:convert';
import 'dart:io';

const String sourceFileTag = 'SF:';
const String lineDataTag = 'DA:';
const String branchDataTag = 'BRDA:';
const String endOfRecord = 'end_of_record';
const String untakenBranch = '-';
const int expectedArgumentCount = 3;
const int lineNumberField = 0;
const int lineHitsField = 1;
const int branchTakenField = 3;

final class FileCoverage {
  const FileCoverage({
    required this.foundLines,
    required this.uncoveredLines,
    required this.foundBranches,
    required this.untakenBranchLines,
  });

  final int foundLines;
  final List<int> uncoveredLines;
  final int foundBranches;
  final List<int> untakenBranchLines;

  int get hitLines => foundLines - uncoveredLines.length;

  int get hitBranches => foundBranches - untakenBranchLines.length;
}

List<String> fieldsOf(String dataLine, String tag) {
  return dataLine.substring(tag.length).split(',');
}

bool isBranchTaken(String takenField) {
  return takenField != untakenBranch && int.parse(takenField) > 0;
}

FileCoverage coverageOfRecord(List<String> recordLines) {
  var foundLines = 0;
  var foundBranches = 0;
  final uncoveredLines = <int>[];
  final untakenBranchLines = <int>[];

  for (final recordLine in recordLines) {
    if (recordLine.startsWith(lineDataTag)) {
      final fields = fieldsOf(recordLine, lineDataTag);
      foundLines += 1;

      if (int.parse(fields[lineHitsField]) == 0) {
        uncoveredLines.add(int.parse(fields[lineNumberField]));
      }
    }

    if (recordLine.startsWith(branchDataTag)) {
      final fields = fieldsOf(recordLine, branchDataTag);
      foundBranches += 1;

      if (!isBranchTaken(fields[branchTakenField])) {
        untakenBranchLines.add(int.parse(fields[lineNumberField]));
      }
    }
  }

  return FileCoverage(
    foundLines: foundLines,
    uncoveredLines: uncoveredLines,
    foundBranches: foundBranches,
    untakenBranchLines: untakenBranchLines,
  );
}

String absoluteSourcePath(String sourcePath, String packageDirectory) {
  final sourceFile = File(sourcePath);

  if (sourceFile.isAbsolute) {
    return sourcePath;
  }

  return File('$packageDirectory/$sourcePath').absolute.path;
}

Map<String, FileCoverage> coverageByFile(
  String lcovReport,
  String packageDirectory,
) {
  final coverage = <String, FileCoverage>{};

  for (final record in lcovReport.split(endOfRecord)) {
    final recordLines = const LineSplitter().convert(record.trim());
    final sourceLines = recordLines.where(
      (recordLine) => recordLine.startsWith(sourceFileTag),
    );

    if (sourceLines.isEmpty) {
      continue;
    }

    final sourcePath = sourceLines.first.substring(sourceFileTag.length);
    final sourceFile = File(absoluteSourcePath(sourcePath, packageDirectory));

    if (!sourceFile.existsSync()) {
      continue;
    }

    final resolvedPath = sourceFile.resolveSymbolicLinksSync();
    coverage[resolvedPath] = coverageOfRecord(recordLines);
  }

  return coverage;
}

String? shortfallOf(String measure, int hit, int found, int minimum) {
  if (found == 0 || hit * 100 >= minimum * found) {
    return null;
  }

  final percent = (hit * 100 / found).toStringAsFixed(2);

  return '$measure: $percent% ($hit/$found) - under $minimum%';
}

List<String> uncoveredLocations(String sourcePath, FileCoverage coverage) {
  final locations = <String>[];

  for (final lineNumber in coverage.uncoveredLines) {
    locations.add('$sourcePath:$lineNumber: no test runs this line');
  }

  for (final lineNumber in coverage.untakenBranchLines) {
    locations.add('$sourcePath:$lineNumber: no test takes this branch');
  }

  return locations;
}

Future<void> main(List<String> arguments) async {
  if (arguments.length != expectedArgumentCount) {
    throw ArgumentError(
      'expected <lcov report> <minimum percent> <package directory>',
    );
  }

  final measured = coverageByFile(
    File(arguments[0]).readAsStringSync(),
    arguments[2],
  );
  final minimum = int.parse(arguments[1]);
  final listing = await utf8.decodeStream(stdin);
  final sourceCoverage = <String, FileCoverage>{};

  for (final sourcePath in const LineSplitter().convert(listing)) {
    if (sourcePath.isEmpty) {
      continue;
    }

    final fileCoverage = measured[File(sourcePath).resolveSymbolicLinksSync()];

    if (fileCoverage != null) {
      sourceCoverage[sourcePath] = fileCoverage;
    }
  }

  var foundLines = 0;
  var hitLines = 0;
  var foundBranches = 0;
  var hitBranches = 0;

  for (final fileCoverage in sourceCoverage.values) {
    foundLines += fileCoverage.foundLines;
    hitLines += fileCoverage.hitLines;
    foundBranches += fileCoverage.foundBranches;
    hitBranches += fileCoverage.hitBranches;
  }

  final shortfalls = [
    shortfallOf('lines', hitLines, foundLines, minimum),
    shortfallOf('branches', hitBranches, foundBranches, minimum),
  ].nonNulls.toList();

  if (shortfalls.isEmpty) {
    return;
  }

  final sortedPaths = sourceCoverage.keys.toList()..sort();

  for (final sourcePath in sortedPaths) {
    final fileCoverage = sourceCoverage[sourcePath]!;
    shortfalls.addAll(uncoveredLocations(sourcePath, fileCoverage));
  }

  for (final shortfall in shortfalls) {
    stdout.writeln(shortfall);
  }
}
