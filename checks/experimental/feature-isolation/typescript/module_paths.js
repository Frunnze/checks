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

function resolveImport(importingFile, specifier) {
  if (!specifier.startsWith(".")) return null;

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
