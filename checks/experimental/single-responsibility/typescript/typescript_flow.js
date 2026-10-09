const { ts, isCallable, isClass, qualified, namesIn } = require("./typescript_bindings");

function statementFlow(node, calls, source) {
  const reads = new Set(), writes = new Set();
  function target(child, read = false) {
    const name = qualified(child);
    if (name) {
      writes.add(name);
      if (read) reads.add(name);
    }
    if (ts.isElementAccessExpression(child)) {
      writes.add(qualified(child.expression));
      visit(child.argumentExpression);
    }
  }
  function visit(child) {
    if (!child || isCallable(child) || isClass(child) || ts.isTypeNode(child)) return;
    if (ts.isIdentifier(child)) {
      reads.add(child.text);
      return;
    }
    if (ts.isVariableDeclaration(child)) {
      for (const name of namesIn(child.name)) writes.add(name);
      visit(child.initializer);
      return;
    }
    if (ts.isBinaryExpression(child) &&
        child.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
        child.operatorToken.kind <= ts.SyntaxKind.LastAssignment) {
      target(child.left, child.operatorToken.kind !== ts.SyntaxKind.EqualsToken);
      visit(child.right);
      return;
    }
    if ((ts.isPrefixUnaryExpression(child) || ts.isPostfixUnaryExpression(child)) &&
        [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(child.operator)) {
      target(child.operand, true);
      return;
    }
    if (ts.isPropertyAccessExpression(child) || ts.isElementAccessExpression(child)) {
      reads.add(qualified(child));
      if (qualified(child.expression) !== "this") visit(child.expression);
      if (ts.isElementAccessExpression(child)) visit(child.argumentExpression);
      return;
    }
    if (ts.isCallExpression(child) || ts.isNewExpression(child)) {
      if (ts.isPropertyAccessExpression(child.expression)) {
        const receiver = qualified(child.expression.expression);
        reads.add(receiver);
        writes.add(receiver);
        visit(child.expression.expression);
      }
      for (const argument of child.arguments ?? []) visit(argument);
      return;
    }
    if (ts.isPropertyAssignment(child)) {
      visit(child.initializer);
      return;
    }
    ts.forEachChild(child, visit);
  }
  visit(node);
  return { line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
    reads: [...reads].filter(Boolean).sort(), writes: [...writes].filter(Boolean).sort(),
    calls: [...calls].sort(), compound: ts.isIfStatement(node) || ts.isIterationStatement(node, false) ||
      ts.isTryStatement(node) || ts.isSwitchStatement(node) };
}

module.exports = { statementFlow };
