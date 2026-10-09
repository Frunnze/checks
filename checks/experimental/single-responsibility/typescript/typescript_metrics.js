const { ts, isCallable, isClass, qualified, namesIn, bindAssignment, localBindings } =
  require("./typescript_bindings");
const { statementFlow } = require("./typescript_flow");

const branching = new Set([
  ts.SyntaxKind.IfStatement, ts.SyntaxKind.ForStatement,
  ts.SyntaxKind.ForInStatement, ts.SyntaxKind.ForOfStatement,
  ts.SyntaxKind.WhileStatement, ts.SyntaxKind.DoStatement,
  ts.SyntaxKind.CatchClause, ts.SyntaxKind.ConditionalExpression,
  ts.SyntaxKind.CaseClause,
]);
const nesting = new Set([...branching, ts.SyntaxKind.TryStatement,
  ts.SyntaxKind.SwitchStatement]);
const booleanOperators = new Set([ts.SyntaxKind.AmpersandAmpersandToken,
  ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken]);

function isReference(node) {
  const parent = node.parent;
  if ((ts.isPropertyAccessExpression(parent) && parent.name === node) ||
      ((ts.isVariableDeclaration(parent) || ts.isPropertyAssignment(parent) ||
        ts.isBindingElement(parent)) && parent.name === node)) return false;
  return true;
}

function dependencyRoot(resolved) {
  const separator = resolved.indexOf(".", resolved.startsWith(".") ? 2 : 0);
  return separator < 0 ? resolved : resolved.slice(0, separator);
}

function runtimeMetrics(source, node, facts, bindings, globals, members, method = false, visible = new Map()) {
  const calls = new Set(), resources = new Set(), links = new Set();
  const locals = new Set(), lines = new Set();
  const localDefinitions = new Set();
  const references = new Set(), foreignData = new Set(), flow = [];
  let blockCalls = new Set(), blockLinks = new Set();
  const parameters = new Set(node.parameters.flatMap(parameter => namesIn(parameter.name)));
  const receivers = new Set(method ? ["this", facts.owner.split(".").at(-1)] : []);
  for (const name of parameters) receivers.delete(name);
  const shadowed = new Set(localBindings(node, new Map()).keys());
  function visit(child, depth = 0) {
    if (isCallable(child) || isClass(child) || ts.isTypeNode(child)) return;
    if (child.kind >= ts.SyntaxKind.FirstToken &&
        child.kind <= ts.SyntaxKind.LastToken &&
        child.kind !== ts.SyntaxKind.JsxText) {
      lines.add(source.getLineAndCharacterOfPosition(child.getStart(source)).line);
    }
    if (ts.isStatement(child) && !ts.isBlock(child) &&
        !ts.isEmptyStatement(child)) facts.statements++;
    if (branching.has(child.kind)) facts.complexity++;
    if (ts.isBinaryExpression(child) &&
        booleanOperators.has(child.operatorToken.kind)) facts.complexity++;
    if (nesting.has(child.kind)) {
      depth++;
      facts.nesting = Math.max(facts.nesting, depth);
    }
    if (ts.isCallExpression(child) || ts.isNewExpression(child)) {
      const call = qualified(child.expression, bindings);
      if (call) { calls.add(call); blockCalls.add(call); }
      const raw = qualified(child.expression);
      const parts = raw.split(".");
      const member = parts.at(-1);
      const internal = (parts.length === 1 && !method && !shadowed.has(member)) ||
        (parts.length === 2 && receivers.has(parts[0]) && !locals.has(parts[0]) && !bindings.has(raw));
      if (members.has(member) && internal) {
        const link = `${facts.owner}.${member}`;
        links.add(link);
        blockLinks.add(link);
      }
      const local = call.startsWith("local:") ? call.slice(6) : "";
      if (visible.has(local) && (!locals.has(local) || localDefinitions.has(local))) {
        const link = visible.get(local);
        links.add(link);
        blockLinks.add(link);
      }
    }
    if (ts.isIdentifier(child) && isReference(child)) {
      const resolved = bindings.get(child.text);
      if (resolved && !resolved.startsWith("local:")) {
        resources.add(`dependency:${dependencyRoot(resolved)}`);
        references.add(resolved);
      } else if (globals.has(child.text) && !bindings.has(child.text)) {
        resources.add(`global:${child.text}`);
      }
    }
    if (ts.isPropertyAccessExpression(child) || ts.isElementAccessExpression(child)) {
      const parts = qualified(child).split(".");
      if (receivers.has(parts[0]) && parts.length >= 2 && !members.has(parts[1])) {
        resources.add(`field:${parts[1]}`);
      }
      const resolved = qualified(child, bindings);
      if (resolved && !resolved.startsWith("local:")) references.add(resolved);
      const parent = child.parent;
      const isCallee = (ts.isCallExpression(parent) || ts.isNewExpression(parent)) && parent.expression === child;
      if (!isCallee && (resolved.startsWith("local:") || parts[0] === "this" || parameters.has(parts[0])) &&
          (!receivers.has(parts[0]) || parts.length > 2)) foreignData.add(qualified(child));
    }
    if (ts.isVariableDeclaration(child)) {
      for (const name of namesIn(child.name)) {
        locals.add(name);
        if (child.initializer && isCallable(child.initializer)) localDefinitions.add(name);
      }
    }
    ts.forEachChild(child, next => visit(next, depth));
    if (ts.isBinaryExpression(child) && ts.isIdentifier(child.left) &&
        child.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
        child.operatorToken.kind <= ts.SyntaxKind.LastAssignment) localDefinitions.delete(child.left.text);
    // Evaluate the initializer with the previous binding before replacing it.
    bindAssignment(child, bindings);
  }
  if (ts.isBlock(node.body) || ts.isSourceFile(node.body)) {
    for (const statement of node.body.statements) {
      blockCalls = new Set();
      blockLinks = new Set();
      visit(statement);
      if (!isCallable(statement) && !isClass(statement)) {
        flow.push({ ...statementFlow(statement, blockCalls, source), links: [...blockLinks].sort() });
      }
    }
  } else {
    visit(node.body);
    facts.statements = Math.max(1, facts.statements);
    flow.push({ ...statementFlow(node.body, blockCalls, source), links: [...blockLinks].sort() });
  }
  return { ...facts, lines: lines.size, locals: locals.size,
    calls: [...calls].sort(), resources: [...resources].sort(),
    links: [...links].sort(), references: [...references].sort(),
    foreign_data: [...foreignData].sort(), flow };
}

module.exports = { runtimeMetrics };
