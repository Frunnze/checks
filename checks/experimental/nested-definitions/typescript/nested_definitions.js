const fs = require("fs");

const typescript = require(process.argv[2]);

function isFunctionScope(node) {
  return (
    typescript.isFunctionDeclaration(node) ||
    typescript.isFunctionExpression(node) ||
    typescript.isArrowFunction(node) ||
    typescript.isMethodDeclaration(node) ||
    typescript.isConstructorDeclaration(node) ||
    typescript.isGetAccessorDeclaration(node) ||
    typescript.isSetAccessorDeclaration(node)
  );
}

function isScope(node) {
  return (
    isFunctionScope(node) ||
    typescript.isClassDeclaration(node) ||
    typescript.isClassExpression(node)
  );
}

function collectScopesFrom(node, found) {
  if (isScope(node)) {
    found.push(node);
    return;
  }

  typescript.forEachChild(node, (child) => collectScopesFrom(child, found));
}

function scopesDirectlyIn(scope) {
  const found = [];

  typescript.forEachChild(scope, (child) => collectScopesFrom(child, found));

  return found;
}

function reportFor(sourceFile, node) {
  const start = sourceFile.getLineAndCharacterOfPosition(node.getStart());
  const name = node.name === undefined ? "(anonymous)" : node.name.text;

  return `${sourceFile.fileName}:${start.line + 1}: ${name}`;
}

function collectNestedFrom(sourceFile, node, found) {
  if (isFunctionScope(node)) {
    for (const inner of scopesDirectlyIn(node)) {
      if (typescript.isFunctionDeclaration(inner)) {
        found.push(reportFor(sourceFile, inner));
      }
    }
  }

  typescript.forEachChild(node, (child) =>
    collectNestedFrom(sourceFile, child, found),
  );
}

function scriptKindOf(filePath) {
  return filePath.endsWith(".tsx")
    ? typescript.ScriptKind.TSX
    : typescript.ScriptKind.TS;
}

function nestedDefinitionsIn(filePath) {
  const sourceFile = typescript.createSourceFile(
    filePath,
    fs.readFileSync(filePath, "utf8"),
    typescript.ScriptTarget.Latest,
    true,
    scriptKindOf(filePath),
  );
  const found = [];

  collectNestedFrom(sourceFile, sourceFile, found);

  return found;
}

const reported = new Set();
const sourcePaths = fs.readFileSync(0, "utf8").split(/\s+/).filter(Boolean);

for (const filePath of sourcePaths) {
  for (const nested of nestedDefinitionsIn(filePath)) reported.add(nested);
}

for (const nested of [...reported].sort()) {
  process.stdout.write(nested + "\n");
}
