const path = require("path");
const {
  importsIn,
  moduleNameOf,
  readPathsFromStandardInput,
  resolveImport,
  sourceRootOf,
} = require("./module_paths");

const SHARED_PACKAGE = "shared";
const FEATURES_DIRECTORY = "features";
const MINIMUM_FEATURES = 2;

const typescript = require(process.argv[2]);

function owningFeatureOf(filePath) {
  const segments = path.resolve(filePath).split(path.sep);
  const index = segments.lastIndexOf(FEATURES_DIRECTORY);

  if (index === -1 || index + 1 >= segments.length) return null;

  return segments[index + 1];
}

function sharedModulesAmong(paths) {
  const modules = new Map();

  for (const filePath of paths) {
    const sourceRoot = sourceRootOf(filePath);

    if (sourceRoot === null) continue;

    const name = moduleNameOf(sourceRoot, filePath);

    if (name.split("/")[0] === SHARED_PACKAGE) modules.set(name, filePath);
  }

  return modules;
}

function sharedImportsIn(filePath, shared) {
  const sourceRoot = sourceRootOf(filePath);
  const found = [];

  if (sourceRoot === null) return found;

  for (const reference of importsIn(typescript, filePath)) {
    const resolved = resolveImport(filePath, reference.specifier);

    if (resolved === null) continue;

    const name = moduleNameOf(sourceRoot, resolved);

    if (shared.has(name)) found.push(name);
  }

  return found;
}

function recordUsage(filePath, shared, callers, kept) {
  const feature = owningFeatureOf(filePath);
  const sourceRoot = sourceRootOf(filePath);
  const ownName =
    sourceRoot === null ? null : moduleNameOf(sourceRoot, filePath);

  for (const name of sharedImportsIn(filePath, shared)) {
    if (feature !== null) {
      callers.get(name).add(feature);
    } else if (ownName !== name) {
      kept.add(name);
    }
  }
}

function lonelyModulesAmong(paths) {
  const shared = sharedModulesAmong(paths);
  const callers = new Map([...shared.keys()].map((name) => [name, new Set()]));
  const kept = new Set();

  for (const filePath of paths) recordUsage(filePath, shared, callers, kept);

  return [...shared.keys()].sort().flatMap((name) => {
    const features = [...callers.get(name)].sort();

    if (kept.has(name) || features.length >= MINIMUM_FEATURES) return [];

    return [reportFor(shared.get(name), features)];
  });
}

function reportFor(filePath, features) {
  const reason =
    features.length === 0
      ? "no feature imports it"
      : `only ${features[0]} imports it`;

  return `${filePath}: ${reason}`;
}

for (const lonely of lonelyModulesAmong(readPathsFromStandardInput())) {
  process.stdout.write(lonely + "\n");
}
