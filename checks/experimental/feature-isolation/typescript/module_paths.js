const fs = require("fs");
const path = require("path");

const SOURCE_ROOT = "src";
const MODULE_EXTENSIONS = [".ts", ".tsx"];
const INDEX_MODULES = ["index.ts", "index.tsx"];

function sourceRootOf(filePath) {
  const parts = path.resolve(filePath).split(path.sep);
  const index = parts.lastIndexOf(SOURCE_ROOT);

  if (index === -1) return null;

  return parts.slice(0, index + 1).join(path.sep);
}

function firstExistingPath(candidates) {
  for (const candidate of candidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }

  return null;
}

function resolveImport(importingFile, specifier) {
  if (!specifier.startsWith(".")) return null;

  const target = path.resolve(path.dirname(importingFile), specifier);
  const withExtension = MODULE_EXTENSIONS.map((suffix) => target + suffix);
  const asDirectory = INDEX_MODULES.map((name) => path.join(target, name));

  return firstExistingPath([...withExtension, ...asDirectory, target]);
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

function moduleNameOf(sourceRoot, filePath) {
  const relative = path.relative(sourceRoot, path.resolve(filePath));

  return relative.replace(/\.tsx?$/, "").split(path.sep).join("/");
}

function readPathsFromStandardInput() {
  return fs.readFileSync(0, "utf8").split(/\s+/).filter(Boolean);
}

module.exports = {
  importsIn,
  moduleNameOf,
  readPathsFromStandardInput,
  resolveImport,
  sourceRootOf,
};
