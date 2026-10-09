const fs = require("node:fs");
const { ts, isCallable, isClass, namesIn, walkScope, importBindings, localBindings } =
  require("./typescript_bindings");
const { runtimeMetrics } = require("./typescript_metrics");
const { classFields } = require("./typescript_fields");
const { projectModules, moduleExports } = require("./typescript_project");

function directScopes(node) {
  const scopes = [];
  ts.forEachChild(node, child => {
    if (isCallable(child) || isClass(child)) scopes.push(child);
    else scopes.push(...directScopes(child));
  });
  return scopes;
}

function scopeName(node, source) {
  if (ts.isConstructorDeclaration(node)) return "constructor";
  if (node.name) return node.name.getText(source);
  if (node.parent && (ts.isVariableDeclaration(node.parent) ||
      ts.isPropertyAssignment(node.parent) || ts.isPropertyDeclaration(node.parent))) {
    return node.parent.name.getText(source);
  }
  const position = source.getLineAndCharacterOfPosition(node.getStart(source));
  return `<anonymous@${position.line + 1}:${position.character}>`;
}

function bindingName(node) {
  if (ts.isFunctionDeclaration(node)) return node.name?.text;
  if (isCallable(node) && ts.isVariableDeclaration(node.parent) && ts.isIdentifier(node.parent.name)) {
    return node.parent.name.text;
  }
  return undefined;
}

function collectScope(source, node, owner, inherited, globals, facts, owners, visible = new Map()) {
  const scopes = directScopes(node);
  const replacedNames = new Set();
  walkScope(node, child => {
    if (ts.isBinaryExpression(child) && ts.isIdentifier(child.left) &&
        child.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
        child.operatorToken.kind <= ts.SyntaxKind.LastAssignment) replacedNames.add(child.left.text);
    if (ts.isVariableDeclaration(child) && (!child.initializer || !isCallable(child.initializer))) {
      for (const name of namesIn(child.name)) replacedNames.add(name);
    }
  });
  visible = new Map(visible);
  if (!isClass(node)) {
    for (const child of scopes) {
      const binding = bindingName(child);
      if (binding && !replacedNames.has(binding)) {
        visible.set(binding, `${owner}.${scopeName(child, source)}`);
      }
    }
  }
  for (const name of replacedNames) visible.delete(name);
  const members = new Set(scopes.filter(isCallable).map(child => scopeName(child, source))
    .filter(name => !replacedNames.has(name)));
  const fields = isClass(node) ? classFields(node, inherited) : new Map();
  for (const child of scopes) {
    const name = `${owner}.${scopeName(child, source)}`;
    const line = source.getLineAndCharacterOfPosition(child.getStart(source)).line + 1;
    const bindings = localBindings(child, inherited);
    const shadowed = localBindings(child, new Map());
    const available = new Map([...visible].filter(([key]) => !shadowed.has(key)));
    if (!child.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.StaticKeyword)) {
      for (const [field, value] of fields) bindings.set(`this.${field}`, value);
    }
    if (isClass(child)) {
      owners.push({ name, line, kind: "class" });
    } else if (child.body) {
      for (const nested of directScopes(child)) {
        const binding = bindingName(nested);
        if (binding && !child.parameters.some(parameter => namesIn(parameter.name).includes(binding))) {
          available.set(binding, `${name}.${scopeName(nested, source)}`);
        }
      }
      const item = { name, line, owner, statements: 0, complexity: 1,
        binding_stable: !replacedNames.has(bindingName(child) ?? scopeName(child, source)),
        nesting: 0, parameters: child.parameters.filter(parameter =>
          parameter.name.getText(source) !== "this").length };
      facts.push(runtimeMetrics(source, child, item, bindings, globals, members, isClass(node), available));
    }
    collectScope(source, child, name, bindings, globals, facts, owners, available);
  }
}

function factsFor(filePath) {
  const kind = filePath.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(filePath, fs.readFileSync(filePath, "utf8"),
    ts.ScriptTarget.Latest, true, kind);
  if (source.parseDiagnostics.length) {
    const diagnostic = source.parseDiagnostics[0];
    const line = source.getLineAndCharacterOfPosition(diagnostic.start ?? 0).line + 1;
    throw new Error(`${filePath}:${line}: ${ts.flattenDiagnosticMessageText(
      diagnostic.messageText, " ")}`);
  }
  const project = projectModules(source);
  const exported = moduleExports(source, scopeName, project.modules);
  const bindings = importBindings(source, project.modules);
  const globals = new Set();
  for (const statement of source.statements) {
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        for (const name of namesIn(declaration.name)) {
          globals.add(name);
          bindings.delete(name);
        }
      }
    } else if ((isCallable(statement) || isClass(statement)) && statement.name) {
      bindings.delete(statement.name.text);
    }
  }
  const facts = [], owners = [{ name: "<module>", line: 1, kind: "module" }];
  const moduleBindings = new Map(bindings);
  facts.push(runtimeMetrics(source, { body: source, parameters: [] },
    { name: "<module-body>", line: 1, owner: "", statements: 0, complexity: 1,
      nesting: 0, parameters: 0, client_only: true },
    moduleBindings, globals, new Set()));
  // Unresolved module values remain globals, not function-local shadows.
  for (const [name, value] of moduleBindings) {
    if (value.startsWith("local:")) moduleBindings.delete(name);
  }
  collectScope(source, source, "<module>", moduleBindings, globals, facts, owners);
  return { path: filePath, callables: facts, owners, ...project, ...exported };
}

try {
  const paths = JSON.parse(fs.readFileSync(0, "utf8"));
  process.stdout.write(JSON.stringify(paths.map(factsFor)));
} catch (error) {
  process.stderr.write(`SRP analysis error: ${error.message}\n`);
  process.exitCode = 2;
}
