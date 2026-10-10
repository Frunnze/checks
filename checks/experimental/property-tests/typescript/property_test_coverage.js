const fs = require("fs");
const path = require("path");
const { describesNoBehaviour } = require("./stateless_definitions");
const { definedIn } = require("./definitions");
const { propertyTestNamesIn } = require("./property_test_names");

const TESTS_DIRECTORY = "tests";
const PARENT_DIRECTORY = "..";
const PROPERTY_MARKER = " property";

const typescript = require(process.argv[2]);
const sourceDirectory = process.argv[3];
const testsDirectory = path.join(
  path.dirname(sourceDirectory),
  TESTS_DIRECTORY,
);

function scriptKindOf(filePath) {
  return filePath.endsWith(".tsx")
    ? typescript.ScriptKind.TSX
    : typescript.ScriptKind.TS;
}

function parse(filePath) {
  return typescript.createSourceFile(
    filePath,
    fs.readFileSync(filePath, "utf8"),
    typescript.ScriptTarget.Latest,
    true,
    scriptKindOf(filePath),
  );
}

function isWithin(directory, filePath) {
  const relative = path.relative(directory, filePath);

  return relative !== "" && relative.split(path.sep)[0] !== PARENT_DIRECTORY;
}

function propertyTestsIn(paths) {
  const found = new Set();

  for (const filePath of paths) {
    for (const name of propertyTestNamesIn(typescript, parse(filePath))) {
      found.add(name);
    }
  }

  return found;
}

function isCovered(name, propertyTests) {
  const expected = name + PROPERTY_MARKER;

  for (const title of propertyTests) {
    if (title.startsWith(expected)) return true;
  }

  return false;
}

function untestedIn(filePath, propertyTests) {
  const sourceFile = parse(filePath);
  const found = [];

  for (const definition of definedIn(typescript, sourceFile)) {
    if (describesNoBehaviour(typescript, definition)) continue;
    if (isCovered(definition.name, propertyTests)) continue;

    const start = sourceFile.getLineAndCharacterOfPosition(
      definition.node.getStart(),
    );

    found.push({
      path: filePath,
      lineNumber: start.line + 1,
      name: definition.name,
    });
  }

  return found;
}

function filesByRole(paths) {
  const roles = { sources: [], tests: [] };

  for (const filePath of paths) {
    if (isWithin(testsDirectory, filePath)) roles.tests.push(filePath);
    else if (isWithin(sourceDirectory, filePath)) roles.sources.push(filePath);
  }

  return roles;
}

const givenPaths = fs.readFileSync(0, "utf8").split("\n").filter(Boolean);
const roles = filesByRole(givenPaths);
const propertyTests = propertyTestsIn(roles.tests);
const reported = [];

for (const filePath of roles.sources) {
  reported.push(...untestedIn(filePath, propertyTests));
}

reported.sort((left, right) =>
  left.path + left.name < right.path + right.name ? -1 : 1,
);

for (const untested of reported) {
  const expected = `"${untested.name} property ..."`;
  process.stdout.write(
    `${untested.path}:${untested.lineNumber}: ${untested.name} ` +
      `needs a test.prop named ${expected}\n`,
  );
}
