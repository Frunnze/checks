const {
  featureSegmentsOf,
  importsIn,
  moduleNameOf,
  readPathsFromStandardInput,
  resolveImport,
} = require("./module_paths");

const SHARED_PACKAGE = "shared";
const MINIMUM_FEATURES = 2;

const typescript = require(process.argv[2]);
const sourceDirectory = process.argv[3];

function owningFeatureOf(filePath) {
  const segments = featureSegmentsOf(sourceDirectory, filePath);

  if (segments === null) return null;

  return segments[0];
}

function sharedModulesAmong(paths) {
  const modules = new Map();

  for (const filePath of paths) {
    const name = moduleNameOf(sourceDirectory, filePath);

    if (name.split("/")[0] === SHARED_PACKAGE) modules.set(name, filePath);
  }

  return modules;
}

function sharedImportsIn(filePath, shared) {
  const found = [];

  for (const reference of importsIn(typescript, filePath)) {
    const resolved = resolveImport(filePath, reference.specifier);

    if (resolved === null) continue;

    const name = moduleNameOf(sourceDirectory, resolved);

    if (shared.has(name)) found.push(name);
  }

  return found;
}

function recordUsage(filePath, shared, callers, kept) {
  const feature = owningFeatureOf(filePath);
  const ownName = moduleNameOf(sourceDirectory, filePath);

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
