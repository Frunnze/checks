const { ts, annotationType, assignedValue, bindAssignment, localBindings,
  qualified, walkScope } = require("./typescript_bindings");

function classFields(node, inherited) {
  const fields = new Map(), declared = new Set(), directTargets = new Set();
  for (const member of node.members) {
    if (!ts.isPropertyDeclaration(member) || member.modifiers?.some(modifier =>
      modifier.kind === ts.SyntaxKind.StaticKeyword)) continue;
    const name = member.name.text;
    if (!name) continue;
    const annotation = annotationType(member.type, inherited);
    const value = annotation || assignedValue(member.initializer, inherited);
    if (value && !value.startsWith("local:")) fields.set(name, value);
    if (annotation) declared.add(name);
  }
  for (const member of node.members) {
    if (!ts.isConstructorDeclaration(member) || !member.body) continue;
    const bindings = localBindings(member, inherited);
    for (const parameter of member.parameters) {
      const value = annotationType(parameter.type, inherited);
      if (value && ts.isIdentifier(parameter.name) && parameter.modifiers?.some(modifier =>
        [ts.SyntaxKind.PublicKeyword, ts.SyntaxKind.PrivateKeyword, ts.SyntaxKind.ProtectedKeyword,
          ts.SyntaxKind.ReadonlyKeyword].includes(modifier.kind))) {
        fields.set(parameter.name.text, value);
        declared.add(parameter.name.text);
      }
    }
    for (const statement of member.body.statements) {
      if (ts.isVariableStatement(statement)) {
        for (const declaration of statement.declarationList.declarations) bindAssignment(declaration, bindings);
      } else if (ts.isExpressionStatement(statement)) {
        bindAssignment(statement.expression, bindings);
        directTargets.add(statement.expression);
      }
    }
    for (const [name, value] of bindings) {
      if (name.startsWith("this.") && name.split(".").length === 2 && !value.startsWith("local:")) {
        if (!fields.has(name.slice(5))) fields.set(name.slice(5), value);
      }
    }
  }
  walkScope(node, child => {
    // walkScope stops at methods; inspect each method body separately below.
    if (!child.body) return;
    walkScope(child.body, expression => {
      if (!ts.isBinaryExpression(expression) || directTargets.has(expression) ||
          expression.operatorToken.kind < ts.SyntaxKind.FirstAssignment ||
          expression.operatorToken.kind > ts.SyntaxKind.LastAssignment) return;
      const name = qualified(expression.left);
      if (name.startsWith("this.") && !declared.has(name.slice(5))) fields.delete(name.slice(5));
    });
  });
  return fields;
}

module.exports = { classFields };
