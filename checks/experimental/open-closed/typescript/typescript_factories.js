const path = require("path");

const ECMASCRIPT_LIBRARY = /^lib\.es/u;
const PROMISE = "Promise";

function declarationNames(typescript, sourceFiles) {
  const abstractions = new Set();

  function visit(node) {
    if (typescript.isInterfaceDeclaration(node)) {
      abstractions.add(node.name.text);
    }
    if (
      typescript.isClassDeclaration(node) &&
      node.name !== undefined &&
      node.modifiers?.some(
        (modifier) => modifier.kind === typescript.SyntaxKind.AbstractKeyword,
      )
    ) {
      abstractions.add(node.name.text);
    }

    typescript.forEachChild(node, visit);
  }

  for (const sourceFile of sourceFiles) visit(sourceFile);

  return abstractions;
}

function annotationName(typescript, node) {
  if (node === undefined) return undefined;
  if (!typescript.isTypeReferenceNode(node)) return undefined;

  const name = node.typeName.getText();

  if (name === PROMISE && node.typeArguments?.length === 1) {
    return annotationName(typescript, node.typeArguments[0]);
  }

  return name;
}

function isInstanceAssignment(typescript, node) {
  return (
    typescript.isBinaryExpression(node) &&
    node.operatorToken.kind === typescript.SyntaxKind.EqualsToken &&
    typescript.isPropertyAccessExpression(node.left) &&
    node.left.expression.kind === typescript.SyntaxKind.ThisKeyword
  );
}

function instanceValues(typescript, owner) {
  const values = [];

  function visit(node) {
    if (isInstanceAssignment(typescript, node)) values.push(node.right);

    typescript.forEachChild(node, visit);
  }

  for (const member of owner.members) {
    if (typescript.isConstructorDeclaration(member)) visit(member);
    if (
      typescript.isPropertyDeclaration(member) &&
      member.initializer !== undefined
    ) {
      values.push(member.initializer);
    }
  }

  return values;
}

function isLanguageBuiltIn(context, expression) {
  const declaration =
    context.checker.getSymbolAtLocation(expression)?.valueDeclaration;

  if (declaration === undefined) return false;

  const sourceFile = declaration.getSourceFile();

  return (
    context.program.isSourceFileDefaultLibrary(sourceFile) &&
    ECMASCRIPT_LIBRARY.test(path.basename(sourceFile.fileName))
  );
}

function newDependencies(context, owner) {
  const found = new Set();

  for (const value of instanceValues(context.typescript, owner)) {
    if (!context.typescript.isNewExpression(value)) continue;
    if (isLanguageBuiltIn(context, value.expression)) continue;

    const name = value.expression.getText().split(".").at(-1);

    if (/^[A-Z]/u.test(name)) found.add(name);
  }

  return found;
}

function factoryReports(context) {
  const abstractions = declarationNames(
    context.typescript,
    context.sourceFiles,
  );
  const reports = [];

  function visit(sourceFile, node) {
    if (
      context.typescript.isClassDeclaration(node) &&
      node.name !== undefined &&
      node.name.text.toLowerCase().endsWith("factory")
    ) {
      const returns = new Set(
        node.members
          .filter(context.typescript.isMethodDeclaration)
          .filter(
            (member) =>
              member.name !== undefined &&
              !member.name.getText().startsWith("_"),
          )
          .map((member) => annotationName(context.typescript, member.type))
          .filter(
            (name) => name !== undefined && abstractions.has(name),
          ),
      );
      const dependencies = newDependencies(context, node);

      if (returns.size > 0 && dependencies.size > 0) {
        const start = sourceFile.getLineAndCharacterOfPosition(
          node.getStart(sourceFile),
        );
        reports.push(
          `${context.displayPathFor(sourceFile)}:${start.line + 1}: ` +
            `${node.name.text} leaks concrete dependencies while creating ` +
            `${[...returns].sort().join(", ")}: ` +
            [...dependencies].sort().join(", "),
        );
      }
    }

    context.typescript.forEachChild(node, (child) => visit(sourceFile, child));
  }

  for (const sourceFile of context.sourceFiles) visit(sourceFile, sourceFile);

  return reports;
}

module.exports = { factoryReports };
