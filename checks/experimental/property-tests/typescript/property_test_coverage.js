const fs = require("fs");
const path = require("path");
const { describesNoBehaviour } = require("./stateless_definitions");
const { definedIn } = require("./definitions");

const SOURCE_DIRECTORY = "src";
const TESTS_DIRECTORY = "tests";
const PROPERTY_MARKER = " property";
const PROPERTY_ASSERTION = "fc.assert(";
const TEST_CALLS = ["it", "test"];

const typescript = require(process.argv[2]);

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

function packageOf(filePath) {
  const segments = path.resolve(filePath).split(path.sep);
  const boundary = segments.lastIndexOf(TESTS_DIRECTORY);

  if (boundary !== -1) return segments.slice(0, boundary).join(path.sep);

  const sourceRoot = segments.lastIndexOf(SOURCE_DIRECTORY);

  return segments.slice(0, sourceRoot).join(path.sep);
}

function isTestPath(filePath) {
  return path.resolve(filePath).split(path.sep).includes(TESTS_DIRECTORY);
}

function collectPropertyTestNames(node, found) {
  const name = propertyTestNameOf(node);

  if (name !== null) found.add(name);

  typescript.forEachChild(node, (child) =>
    collectPropertyTestNames(child, found),
  );
}

function isTestCall(node) {
  return (
    typescript.isIdentifier(node.expression) &&
    TEST_CALLS.includes(node.expression.text)
  );
}

function propertyTestNameOf(node) {
  if (!typescript.isCallExpression(node)) return null;
  if (!isTestCall(node)) return null;

  const title = node.arguments[0];

  if (title === undefined) return null;
  if (!typescript.isStringLiteralLike(title)) return null;
  if (!node.getText().includes(PROPERTY_ASSERTION)) return null;

  return title.text;
}

function propertyTestNamesIn(paths) {
  const found = new Set();

  for (const filePath of paths) {
    collectPropertyTestNames(parse(filePath), found);
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

function groupByPackage(paths) {
  const grouped = new Map();

  for (const filePath of paths) {
    const owner = packageOf(filePath);
    const bucket = grouped.get(owner) ?? { sources: [], tests: [] };

    if (isTestPath(filePath)) bucket.tests.push(filePath);
    else bucket.sources.push(filePath);

    grouped.set(owner, bucket);
  }

  return grouped;
}

const givenPaths = fs.readFileSync(0, "utf8").split(/\s+/).filter(Boolean);
const reported = [];

for (const bucket of groupByPackage(givenPaths).values()) {
  const propertyTests = propertyTestNamesIn(bucket.tests);

  for (const filePath of bucket.sources) {
    reported.push(...untestedIn(filePath, propertyTests));
  }
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
