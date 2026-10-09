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
  if (typescript.isTypeReferenceNode(node)) return node.typeName.getText();

  return undefined;
}

function newDependencies(typescript, owner) {
  const found = new Set();

  function visit(node) {
    if (typescript.isNewExpression(node)) {
      const name = node.expression.getText().split(".").at(-1);

      if (/^[A-Z]/u.test(name)) found.add(name);
    }

    typescript.forEachChild(node, visit);
  }

  for (const member of owner.members) {
    if (
      typescript.isConstructorDeclaration(member) ||
      typescript.isPropertyDeclaration(member)
    ) {
      visit(member);
    }
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
      const dependencies = newDependencies(context.typescript, node);

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
