const FAST_CHECK_MODULE = "fast-check";
const FAST_CHECK_SCOPE = "@fast-check/";
const FAST_CHECK_NAMESPACE = "fc";
const ASSERT_FUNCTION = "assert";
const PROPERTY_RUNNER = "prop";
const TEST_CALLS = ["it", "test"];

function isFastCheckImport(typescript, statement) {
  if (!typescript.isImportDeclaration(statement)) return false;
  if (statement.importClause === undefined) return false;

  const specifier = statement.moduleSpecifier;

  return (
    typescript.isStringLiteral(specifier) &&
    (specifier.text === FAST_CHECK_MODULE ||
      specifier.text.startsWith(FAST_CHECK_SCOPE))
  );
}

function recordNamedBindings(typescript, namedBindings, bindings) {
  if (typescript.isNamespaceImport(namedBindings)) {
    bindings.namespaces.add(namedBindings.name.text);
    return;
  }

  for (const element of namedBindings.elements) {
    const imported = (element.propertyName ?? element.name).text;

    if (imported === FAST_CHECK_NAMESPACE) {
      bindings.namespaces.add(element.name.text);
    }

    if (imported === ASSERT_FUNCTION) {
      bindings.assertions.add(element.name.text);
    }
  }
}

function fastCheckBindingsIn(typescript, sourceFile) {
  const bindings = {
    namespaces: new Set([FAST_CHECK_NAMESPACE]),
    assertions: new Set(),
  };

  for (const statement of sourceFile.statements) {
    if (!isFastCheckImport(typescript, statement)) continue;

    const clause = statement.importClause;

    if (clause.name !== undefined) bindings.namespaces.add(clause.name.text);

    if (clause.namedBindings !== undefined) {
      recordNamedBindings(typescript, clause.namedBindings, bindings);
    }
  }

  return bindings;
}

function isPropertyAssertion(typescript, node, bindings) {
  if (!typescript.isCallExpression(node)) return false;

  const callee = node.expression;

  if (typescript.isIdentifier(callee)) {
    return bindings.assertions.has(callee.text);
  }

  return (
    typescript.isPropertyAccessExpression(callee) &&
    typescript.isIdentifier(callee.expression) &&
    bindings.namespaces.has(callee.expression.text) &&
    callee.name.text === ASSERT_FUNCTION
  );
}

function callsPropertyAssertion(typescript, node, bindings) {
  if (isPropertyAssertion(typescript, node, bindings)) return true;

  const found = typescript.forEachChild(node, (child) =>
    callsPropertyAssertion(typescript, child, bindings),
  );

  return found === true;
}

function isTestCallee(typescript, callee) {
  return typescript.isIdentifier(callee) && TEST_CALLS.includes(callee.text);
}

function isPropertyRunner(typescript, callee) {
  return (
    typescript.isCallExpression(callee) &&
    typescript.isPropertyAccessExpression(callee.expression) &&
    isTestCallee(typescript, callee.expression.expression) &&
    callee.expression.name.text === PROPERTY_RUNNER
  );
}

function titleOf(typescript, call) {
  const title = call.arguments[0];

  if (title === undefined) return null;
  if (!typescript.isStringLiteralLike(title)) return null;

  return title.text;
}

function propertyTestNameOf(typescript, node, bindings) {
  if (!typescript.isCallExpression(node)) return null;

  if (isPropertyRunner(typescript, node.expression)) {
    return titleOf(typescript, node);
  }

  if (!isTestCallee(typescript, node.expression)) return null;

  const title = titleOf(typescript, node);

  if (title === null) return null;
  if (!callsPropertyAssertion(typescript, node, bindings)) return null;

  return title;
}

function collectPropertyTestNames(typescript, node, bindings, found) {
  const name = propertyTestNameOf(typescript, node, bindings);

  if (name !== null) found.add(name);

  typescript.forEachChild(node, (child) =>
    collectPropertyTestNames(typescript, child, bindings, found),
  );
}

function propertyTestNamesIn(typescript, sourceFile) {
  const bindings = fastCheckBindingsIn(typescript, sourceFile);
  const found = new Set();

  collectPropertyTestNames(typescript, sourceFile, bindings, found);

  return found;
}

module.exports = { propertyTestNamesIn };
