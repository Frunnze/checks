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

const compilerOptionsByConfig = new Map();

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

function compilerOptionsIn(typescript, config) {
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

  return parsed.options;
}

function compilerOptionsFor(typescript, importingFile) {
  const config = typescript.findConfigFile(
    path.dirname(path.resolve(importingFile)),
    typescript.sys.fileExists,
  );

  if (config === undefined) return null;

  if (!compilerOptionsByConfig.has(config)) {
    compilerOptionsByConfig.set(config, compilerOptionsIn(typescript, config));
  }

  return compilerOptionsByConfig.get(config);
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

function lineNumberAt(text, position) {
  return text.slice(0, position).split("\n").length;
}

function importsIn(typescript, filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  const scanned = typescript.preProcessFile(text, true, true);

  return scanned.importedFiles.map((reference) => ({
    specifier: reference.fileName,
    lineNumber: lineNumberAt(text, reference.pos),
  }));
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
