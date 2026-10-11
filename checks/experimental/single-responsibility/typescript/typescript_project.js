const path = require("node:path");
const { ts, isCallable, isClass, qualified, namesIn, annotationType } = require("./typescript_bindings");

const projectsCache = new Map();

function configuredProject(config) {
  if (!projectsCache.has(config)) {
    const read = ts.readConfigFile(config, ts.sys.readFile);
    if (read.error) throw new Error(`${config}: ${ts.flattenDiagnosticMessageText(read.error.messageText, " ")}`);
    const parsed = ts.parseJsonConfigFileContent(read.config, ts.sys, path.dirname(config), undefined, config);
    // The CLI selects the files to analyze, independently of tsconfig include/exclude.
    const errors = parsed.errors.filter(error => error.code !== 18003);
    if (errors.length) throw new Error(`${config}: ${ts.flattenDiagnosticMessageText(errors[0].messageText, " ")}`);
    const files = new Set(parsed.fileNames.map(fileName =>
      path.resolve(fileName)));
    projectsCache.set(config, { options: parsed.options, config, files,
      references: parsed.projectReferences ?? [] });
  }
  return projectsCache.get(config);
}

function owningProject(config, filePath) {
  const pending = [config], visited = new Set();
  while (pending.length) {
    const candidate = pending.shift();
    if (visited.has(candidate)) continue;
    visited.add(candidate);
    const project = configuredProject(candidate);
    if (project.files.has(filePath)) return project;
    for (const reference of project.references) {
      pending.push(ts.resolveProjectReferencePath(reference));
    }
  }
  return configuredProject(config);
}

function compilerOptions(filePath) {
  const file = path.resolve(filePath);
  const config = process.argv[3] ||
    ts.findConfigFile(path.dirname(file), ts.sys.fileExists);
  if (!config) return { options: { moduleResolution: ts.ModuleResolutionKind.Node10 }, config: null };
  return owningProject(config, file);
}

function projectModules(source) {
  const { options, config } = compilerOptions(source.fileName);
  const modules = Object.create(null);
  function visit(node) {
    let specifier = node.moduleSpecifier;
    if (ts.isExternalModuleReference(node)) specifier = node.expression;
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "require" &&
        node.arguments.length === 1) specifier = node.arguments[0];
    if (specifier && ts.isStringLiteral(specifier)) {
      const resolved = ts.resolveModuleName(specifier.text, path.resolve(source.fileName), options, ts.sys).resolvedModule;
      if (resolved) modules[specifier.text] = path.resolve(resolved.resolvedFileName);
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
  return { modules, config };
}

function moduleExports(source, scopeName, bindings) {
  const exports = {}, stars = [];
  let exportEquals;
  const declarations = new Map();
  for (const statement of source.statements) {
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        for (const name of namesIn(declaration.name)) {
          if (declaration.initializer && (isCallable(declaration.initializer) || isClass(declaration.initializer))) {
            declarations.set(name, `<module>.${scopeName(declaration.initializer, source)}`);
          }
        }
      }
    } else if ((isCallable(statement) || isClass(statement)) &&
               statement.name) {
      declarations.set(statement.name.text,
        `<module>.${scopeName(statement, source)}`);
    }
  }
  function local(name) {
    if (declarations.has(name)) return declarations.get(name);
    const value = bindings.get(name) ?? `local:${name}`;
    if (!value.startsWith("local:")) return { reference: value };
    const target = value.slice("local:".length);
    return declarations.get(target) ?? `<module>.${target}`;
  }
  for (const statement of source.statements) {
    if (ts.isExportDeclaration(statement)) {
      const module = statement.moduleSpecifier?.text;
      if (!statement.exportClause) {
        if (module) stars.push(module);
      } else if (ts.isNamedExports(statement.exportClause)) {
        for (const element of statement.exportClause.elements) {
          const name = (element.propertyName ?? element.name).text;
          exports[element.name.text] = module ? { reference: `${module}.${name}` } : local(name);
        }
      } else if (module) {
        exports[statement.exportClause.name.text] = { reference: module };
      }
    } else if (ts.isExportAssignment(statement)) {
      let expression = statement.expression;
      while (ts.isParenthesizedExpression(expression)) expression = expression.expression;
      const name = qualified(expression);
      const target = isCallable(expression) || isClass(expression)
        ? `<module>.${scopeName(expression, source)}` : name ? local(name) : undefined;
      if (statement.isExportEquals) exportEquals = target;
      else if (target) exports.default = target;
    } else if (statement.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)) {
      const isDefault = statement.modifiers.some(modifier => modifier.kind === ts.SyntaxKind.DefaultKeyword);
      if (isCallable(statement) || isClass(statement)) {
        const name = scopeName(statement, source);
        exports[isDefault ? "default" : name] = `<module>.${name}`;
      } else if (ts.isVariableStatement(statement)) {
        for (const declaration of statement.declarationList.declarations) {
          for (const name of namesIn(declaration.name)) exports[name] = local(name);
        }
      } else if (ts.isTypeAliasDeclaration(statement)) {
        const reference = annotationType(statement.type, bindings);
        if (reference) exports[statement.name.text] = { reference };
      }
    }
  }
  return { exports, export_stars: stars, export_equals: exportEquals };
}

module.exports = { projectModules, moduleExports };
