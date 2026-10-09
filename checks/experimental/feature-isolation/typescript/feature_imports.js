const path = require("path");
const {
  importsIn,
  readPathsFromStandardInput,
  resolveImport,
  sourceRootOf,
} = require("./module_paths");

const FEATURES_DIRECTORY = "features";
const FEATURES_PREFIX = "features.";

const typescript = require(process.argv[2]);

function featureChainOf(sourceRoot, filePath) {
  const featuresRoot = path.join(sourceRoot, FEATURES_DIRECTORY);
  const relative = path.relative(featuresRoot, path.resolve(filePath));

  if (relative.startsWith("..") || relative === "") return null;

  return relative.split(path.sep).slice(0, -1);
}

function isPrefix(shorter, longer) {
  return shorter.every((segment, index) => longer[index] === segment);
}

function sharedDepth(importer, imported) {
  let depth = 0;

  while (importer[depth] !== undefined) {
    if (importer[depth] !== imported[depth]) break;

    depth += 1;
  }

  return depth;
}

function crossingBetween(importer, imported) {
  if (isPrefix(importer, imported)) return null;
  if (isPrefix(imported, importer)) return null;

  const divergence = sharedDepth(importer, imported);

  return FEATURES_PREFIX + imported.slice(0, divergence + 1).join(".");
}

function crossingsIn(filePath) {
  const sourceRoot = sourceRootOf(filePath);

  if (sourceRoot === null) return [];

  const importerChain = featureChainOf(sourceRoot, filePath);

  if (importerChain === null || importerChain.length === 0) return [];

  return crossedImportsIn(filePath, sourceRoot, importerChain);
}

function crossedImportsIn(filePath, sourceRoot, importerChain) {
  const found = [];

  for (const reference of importsIn(typescript, filePath)) {
    const resolved = resolveImport(filePath, reference.specifier);

    if (resolved === null) continue;

    const importedChain = featureChainOf(sourceRoot, resolved);

    if (importedChain === null) continue;

    const crossed = crossingBetween(importerChain, importedChain);

    if (crossed !== null) {
      found.push(`${filePath}:${reference.lineNumber}: ${crossed}`);
    }
  }

  return found;
}

const reported = new Set();

for (const filePath of readPathsFromStandardInput()) {
  for (const crossing of crossingsIn(filePath)) reported.add(crossing);
}

for (const crossing of [...reported].sort()) {
  process.stdout.write(crossing + "\n");
}
