const fs = require("fs");
const path = require("path");

const FEATURES_DIRECTORY = "features";
const PARENT_DIRECTORY = "..";
const INDEX_MODULE = "index";
const MODULE_EXTENSIONS = [".ts", ".tsx", ".d.ts"];
const EMITTED_EXTENSIONS = new Map([
  [".js", MODULE_EXTENSIONS],
  [".mjs", [".mts", ".d.mts"]],
  [".cjs", [".cts", ".d.cts"]],
]);
const TYPESCRIPT_EXTENSION = /(\.d)?\.(tsx?|mts|cts)$/;
const NO_INPUTS_FOUND = 18003;
const REQUIRE_FUNCTION = "require";

const projectsByConfig = new Map();

function featureSegmentsOf(sourceDirectory, filePath) {
  const featuresRoot = path.join(sourceDirectory, FEATURES_DIRECTORY);
  const relative = path.relative(featuresRoot, filePath);
  const segments = relative.split(path.sep);

  if (relative === "" || segments[0] === PARENT_DIRECTORY) return null;

  return segments;
}

function firstExistingPath(candidates) {
  for (const candidate of candidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }

  return null;
}

function modulesNamed(target) {
  const extension = path.extname(target);
  const sourceExtensions = EMITTED_EXTENSIONS.get(extension);

  if (sourceExtensions !== undefined) {
    const stem = target.slice(0, -extension.length);

    return sourceExtensions.map((suffix) => stem + suffix);
  }

  const asFile = MODULE_EXTENSIONS.map((suffix) => target + suffix);
  const asDirectory = MODULE_EXTENSIONS.map((suffix) =>
    path.join(target, INDEX_MODULE + suffix),
  );

  return [...asFile, ...asDirectory];
}

function configErrorOf(typescript, config, diagnostic) {
  const message = typescript.flattenDiagnosticMessageText(
    diagnostic.messageText,
    " ",
  );

  return new Error(`${config}: ${message}`);
}

function projectIn(typescript, config) {
  const read = typescript.readConfigFile(config, typescript.sys.readFile);

  if (read.error !== undefined) {
    throw configErrorOf(typescript, config, read.error);
  }

  const parsed = typescript.parseJsonConfigFileContent(
    read.config,
    typescript.sys,
    path.dirname(config),
    undefined,
    config,
  );
  const errors = parsed.errors.filter(
    (error) => error.code !== NO_INPUTS_FOUND,
  );

  if (errors.length > 0) throw configErrorOf(typescript, config, errors[0]);

  return {
    options: parsed.options,
    files: new Set(parsed.fileNames.map((fileName) => path.resolve(fileName))),
    references: parsed.projectReferences ?? [],
  };
}

function configuredProject(typescript, config) {
  if (!projectsByConfig.has(config)) {
    projectsByConfig.set(config, projectIn(typescript, config));
  }

  return projectsByConfig.get(config);
}

function owningProject(typescript, config, filePath) {
  const pending = [config];
  const visited = new Set();

  while (pending.length > 0) {
    const candidate = pending.shift();

    if (visited.has(candidate)) continue;
    visited.add(candidate);

    const project = configuredProject(typescript, candidate);

    if (project.files.has(filePath)) return project;
    for (const reference of project.references) {
      pending.push(typescript.resolveProjectReferencePath(reference));
    }
  }

  return configuredProject(typescript, config);
}

function compilerOptionsFor(typescript, importingFile) {
  const filePath = path.resolve(importingFile);
  const config = typescript.findConfigFile(
    path.dirname(filePath),
    typescript.sys.fileExists,
  );

  if (config === undefined) return null;

  return owningProject(typescript, config, filePath).options;
}

function resolveProjectImport(typescript, importingFile, specifier) {
  const options = compilerOptionsFor(typescript, importingFile);

  if (options === null) return null;

  const resolved = typescript.resolveModuleName(
    specifier,
    path.resolve(importingFile),
    options,
    typescript.sys,
  ).resolvedModule;

  if (resolved === undefined || resolved.isExternalLibraryImport) return null;

  return resolved.resolvedFileName;
}

function resolveImport(typescript, importingFile, specifier) {
  if (!specifier.startsWith(".")) {
    return resolveProjectImport(typescript, importingFile, specifier);
  }

  const target = path.join(path.dirname(importingFile), specifier);

  return firstExistingPath([...modulesNamed(target), target]);
}

function isModuleCall(typescript, node) {
  if (!typescript.isCallExpression(node) || node.arguments.length === 0) {
    return false;
  }

  const callee = node.expression;

  return (
    callee.kind === typescript.SyntaxKind.ImportKeyword ||
    (typescript.isIdentifier(callee) && callee.text === REQUIRE_FUNCTION)
  );
}

function moduleSpecifierOf(typescript, node) {
  if (
    typescript.isImportDeclaration(node) ||
    typescript.isExportDeclaration(node)
  ) {
    return node.moduleSpecifier;
  }
  if (typescript.isExternalModuleReference(node)) return node.expression;
  if (
    typescript.isImportTypeNode(node) &&
    typescript.isLiteralTypeNode(node.argument)
  ) {
    return node.argument.literal;
  }
  if (isModuleCall(typescript, node)) return node.arguments[0];

  return undefined;
}

function collectImports(typescript, sourceFile, node, found) {
  const specifier = moduleSpecifierOf(typescript, node);

  if (specifier !== undefined && typescript.isStringLiteralLike(specifier)) {
    const start = sourceFile.getLineAndCharacterOfPosition(
      specifier.getStart(sourceFile),
    );
    found.push({ specifier: specifier.text, lineNumber: start.line + 1 });
  }

  typescript.forEachChild(node, (child) =>
    collectImports(typescript, sourceFile, child, found),
  );
}

function importsIn(typescript, filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  const sourceFile = typescript.createSourceFile(
    filePath,
    text,
    typescript.ScriptTarget.Latest,
    true,
  );
  const found = [];

  collectImports(typescript, sourceFile, sourceFile, found);

  return found;
}

function moduleNameOf(sourceDirectory, filePath) {
  const relative = path.relative(sourceDirectory, filePath);

  return relative.replace(TYPESCRIPT_EXTENSION, "").split(path.sep).join("/");
}

function readPathsFromStandardInput() {
  return fs.readFileSync(0, "utf8").split("\n").filter(Boolean);
}

module.exports = {
  featureSegmentsOf,
  importsIn,
  moduleNameOf,
  readPathsFromStandardInput,
  resolveImport,
};
