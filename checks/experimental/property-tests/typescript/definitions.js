function isFunctionValue(typescript, node) {
  return (
    node !== undefined &&
    (typescript.isArrowFunction(node) || typescript.isFunctionExpression(node))
  );
}

function objectMethodsIn(typescript, literal) {
  const found = [];

  for (const member of literal.properties) {
    if (typescript.isMethodDeclaration(member)) {
      found.push({ name: member.name.getText(), node: member });
    }

    if (
      typescript.isPropertyAssignment(member) &&
      isFunctionValue(typescript, member.initializer)
    ) {
      found.push({ name: member.name.getText(), node: member.initializer });
    }
  }

  return found;
}

function boundFunctionsIn(typescript, statement) {
  const found = [];

  for (const declaration of statement.declarationList.declarations) {
    const initialiser = declaration.initializer;

    if (initialiser === undefined) continue;
    if (!typescript.isIdentifier(declaration.name)) continue;

    if (isFunctionValue(typescript, initialiser)) {
      found.push({ name: declaration.name.text, node: initialiser });
    } else if (typescript.isObjectLiteralExpression(initialiser)) {
      found.push(...objectMethodsIn(typescript, initialiser));
    }
  }

  return found;
}

function methodsIn(typescript, declaration) {
  const found = [];

  for (const member of declaration.members) {
    const isMethod =
      typescript.isMethodDeclaration(member) ||
      typescript.isGetAccessorDeclaration(member) ||
      typescript.isSetAccessorDeclaration(member);

    if (isMethod && member.name !== undefined) {
      found.push({ name: member.name.getText(), node: member });
    }
  }

  return found;
}

function definitionsFrom(typescript, statement) {
  if (typescript.isFunctionDeclaration(statement)) {
    return statement.name === undefined
      ? []
      : [{ name: statement.name.text, node: statement }];
  }

  if (typescript.isVariableStatement(statement)) {
    return boundFunctionsIn(typescript, statement);
  }

  if (typescript.isClassDeclaration(statement)) {
    return methodsIn(typescript, statement);
  }

  return [];
}

function definedIn(typescript, sourceFile) {
  const found = [];

  for (const statement of sourceFile.statements) {
    found.push(...definitionsFrom(typescript, statement));
  }

  return found;
}

module.exports = { definedIn };
