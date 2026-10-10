const fs = require("fs");

const typescript = require(process.argv[2]);

const JOINED_NAME = /(And|Or)[A-Z]/;
const MEMBER_NAME = /^[a-z_$]/;

function isFunctionValue(node) {
  return (
    node !== undefined &&
    (typescript.isArrowFunction(node) || typescript.isFunctionExpression(node))
  );
}

function isNamedDeclaration(node) {
  return (
    typescript.isFunctionDeclaration(node) ||
    typescript.isClassDeclaration(node) ||
    typescript.isInterfaceDeclaration(node) ||
    typescript.isTypeAliasDeclaration(node) ||
    typescript.isEnumDeclaration(node) ||
    typescript.isVariableDeclaration(node)
  );
}

function isMemberDefinition(node) {
  return (
    typescript.isMethodDeclaration(node) ||
    typescript.isMethodSignature(node) ||
    typescript.isGetAccessorDeclaration(node) ||
    typescript.isSetAccessorDeclaration(node) ||
    (typescript.isPropertyDeclaration(node) &&
      isFunctionValue(node.initializer))
  );
}

function joinedNameOf(node) {
  if (node.name === undefined || !typescript.isIdentifier(node.name)) {
    return null;
  }

  const name = node.name.text;

  if (!JOINED_NAME.test(name)) return null;
  if (isNamedDeclaration(node)) return node.name;
  if (isMemberDefinition(node) && MEMBER_NAME.test(name)) return node.name;

  return null;
}

function collectJoinedLines(sourceFile, node, lineNumbers) {
  const name = joinedNameOf(node);

  if (name !== null) {
    const start = sourceFile.getLineAndCharacterOfPosition(name.getStart());
    lineNumbers.add(start.line + 1);
  }

  typescript.forEachChild(node, (child) =>
    collectJoinedLines(sourceFile, child, lineNumbers),
  );
}

function scriptKindOf(filePath) {
  return filePath.endsWith(".tsx")
    ? typescript.ScriptKind.TSX
    : typescript.ScriptKind.TS;
}

function joinedNamesIn(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  const sourceFile = typescript.createSourceFile(
    filePath,
    text,
    typescript.ScriptTarget.Latest,
    true,
    scriptKindOf(filePath),
  );
  const lineNumbers = new Set();

  collectJoinedLines(sourceFile, sourceFile, lineNumbers);

  const lines = text.split("\n");

  return [...lineNumbers]
    .sort((first, second) => first - second)
    .map((lineNumber) => `${filePath}:${lineNumber}:${lines[lineNumber - 1]}`);
}

const sourcePaths = fs.readFileSync(0, "utf8").split("\n").filter(Boolean);

for (const filePath of sourcePaths) {
  for (const finding of joinedNamesIn(filePath)) {
    process.stdout.write(finding + "\n");
  }
}
