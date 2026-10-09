const ts = require(process.argv[2]);

function isCallable(node) {
  return ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) ||
    ts.isArrowFunction(node) || ts.isMethodDeclaration(node) ||
    ts.isConstructorDeclaration(node) || ts.isGetAccessorDeclaration(node) ||
    ts.isSetAccessorDeclaration(node);
}

function isClass(node) {
  return ts.isClassDeclaration(node) || ts.isClassExpression(node);
}

function qualified(node, bindings) {
  if (!node) return "";
  if (ts.isIdentifier(node)) return bindings
    ? bindings.get(node.text) ?? `local:${node.text}` : node.text;
  if (node.kind === ts.SyntaxKind.ThisKeyword) return "this";
  if (ts.isPropertyAccessExpression(node) || ts.isQualifiedName(node)) {
    if (bindings?.has(qualified(node))) return bindings.get(qualified(node));
    const base = qualified(node.expression ?? node.left, bindings);
    return base ? `${base}.${(node.name ?? node.right).text}` : "";
  }
  if (ts.isElementAccessExpression(node) &&
      ts.isStringLiteral(node.argumentExpression)) {
    if (bindings?.has(qualified(node))) return bindings.get(qualified(node));
    return `${qualified(node.expression, bindings)}.${node.argumentExpression.text}`;
  }
  if (ts.isCallExpression(node) || ts.isNewExpression(node) ||
      ts.isParenthesizedExpression(node) || ts.isAsExpression(node) ||
      ts.isNonNullExpression(node) || ts.isAwaitExpression(node)) {
    return qualified(node.expression, bindings);
  }
  return "";
}

function namesIn(name) {
  if (ts.isIdentifier(name)) return [name.text];
  if (ts.isObjectBindingPattern(name) || ts.isArrayBindingPattern(name)) {
    return name.elements.flatMap(element =>
      ts.isBindingElement(element) ? namesIn(element.name) : []);
  }
  return [];
}

function walkScope(node, visit) {
  ts.forEachChild(node, child => {
    visit(child);
    if (isCallable(child) || isClass(child)) return;
    walkScope(child, visit);
  });
}

function importBindings(source, modules = {}) {
  const bindings = new Map([
    ["fetch", "global.fetch"], ["document", "global.document"],
    ["localStorage", "global.localStorage"],
    ["sessionStorage", "global.sessionStorage"],
    ["require", "global.require"],
  ]);
  for (const statement of source.statements) {
    if (ts.isImportEqualsDeclaration(statement) && ts.isExternalModuleReference(statement.moduleReference) &&
        statement.moduleReference.expression && ts.isStringLiteral(statement.moduleReference.expression)) {
      bindings.set(statement.name.text, statement.moduleReference.expression.text);
      continue;
    }
    if (!ts.isImportDeclaration(statement) || !statement.importClause) continue;
    const clause = statement.importClause;
    const module = statement.moduleSpecifier.text;
    if (clause.name) {
      const local = module.startsWith(".") || (modules[module] && !modules[module].includes("/node_modules/"));
      bindings.set(clause.name.text, local ? `${module}.default` : module);
    }
    if (clause.namedBindings && ts.isNamespaceImport(clause.namedBindings)) {
      bindings.set(clause.namedBindings.name.text, module);
    } else if (clause.namedBindings) {
      for (const element of clause.namedBindings.elements) {
        bindings.set(element.name.text,
          `${module}.${(element.propertyName ?? element.name).text}`);
      }
    }
  }
  for (const statement of source.statements) {
    if (ts.isTypeAliasDeclaration(statement)) {
      const value = annotationType(statement.type, bindings);
      if (value) bindings.set(statement.name.text, value);
    }
  }
  return bindings;
}

function localBindings(node, inherited) {
  const bindings = new Map(inherited);
  walkScope(node, child => {
    if (ts.isVariableDeclaration(child)) {
      for (const name of namesIn(child.name)) bindings.set(name, `local:${name}`);
    } else if ((ts.isFunctionDeclaration(child) || ts.isClassDeclaration(child)) &&
               child.name) {
      bindings.set(child.name.text, `local:${child.name.text}`);
    }
  });
  for (const parameter of node.parameters ?? []) {
    for (const name of namesIn(parameter.name)) bindings.set(name, `local:${name}`);
    if (ts.isIdentifier(parameter.name) && parameter.type) {
      const annotation = annotationType(parameter.type, inherited);
      if (annotation) {
        bindings.set(parameter.name.text, annotation);
      }
    }
  }
  return bindings;
}

function annotationType(node, bindings) {
  if (!node) return "";
  if (ts.isParenthesizedTypeNode(node)) return annotationType(node.type, bindings);
  if (ts.isUnionTypeNode(node)) {
    const values = node.types.filter(type => type.kind !== ts.SyntaxKind.UndefinedKeyword &&
      !(ts.isLiteralTypeNode(type) && type.literal.kind === ts.SyntaxKind.NullKeyword));
    const types = new Set(values.map(type => annotationType(type, bindings)));
    return types.size === 1 && !types.has("") ? [...types][0] : "";
  }
  const resolved = ts.isTypeReferenceNode(node) ? qualified(node.typeName, bindings) : "";
  return resolved && !resolved.startsWith("local:") ? resolved : "";
}

function assignedValue(value, bindings) {
  while (value && (ts.isParenthesizedExpression(value) || ts.isAsExpression(value) ||
      ts.isNonNullExpression(value) || ts.isSatisfiesExpression(value))) value = value.expression;
  if (value && ts.isCallExpression(value) && qualified(value.expression, bindings) === "global.require" &&
      value.arguments.length === 1 && ts.isStringLiteral(value.arguments[0])) return value.arguments[0].text;
  return value && !ts.isCallExpression(value) && !ts.isAwaitExpression(value)
    ? qualified(value, bindings) : "";
}

function bindAssignment(node, bindings) {
  let name, value;
  if (ts.isVariableDeclaration(node)) {
    name = node.name;
    value = node.initializer;
  } else if (ts.isBinaryExpression(node) &&
             node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
    name = node.left;
    value = node.right;
  }
  if (!name) return;
  const resolved = annotationType(node.type, bindings) || assignedValue(value, bindings);
  if (ts.isObjectBindingPattern(name)) {
    for (const element of name.elements) {
      if (!ts.isIdentifier(element.name)) continue;
      const property = element.propertyName ?? element.name;
      const member = !element.dotDotDotToken && !element.initializer &&
        (ts.isIdentifier(property) || ts.isStringLiteral(property)) && resolved
        ? `${resolved}.${property.text}` : `local:${element.name.text}`;
      bindings.set(element.name.text, member);
    }
    return;
  }
  if (!(ts.isIdentifier(name) || ts.isPropertyAccessExpression(name) || ts.isElementAccessExpression(name))) return;
  const target = qualified(name);
  if (target) bindings.set(target, resolved || `local:${target}`);
}

module.exports = { ts, isCallable, isClass, qualified, namesIn, walkScope,
  importBindings, localBindings, bindAssignment, annotationType, assignedValue };
