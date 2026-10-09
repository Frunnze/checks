function namedType(type, displayPathFor) {
  const symbol = type.aliasSymbol ?? type.getSymbol();

  if (symbol === undefined) return undefined;

  const name = symbol.getName();

  if (name === "__type" || name === "unknown" || name === "any") {
    return undefined;
  }

  const declaration = symbol.declarations?.[0];
  const declarationSource = declaration?.getSourceFile();
  const declarationPath =
    declarationSource === undefined ? "" : displayPathFor(declarationSource);

  return {
    key: `${declarationPath}::${name}`,
    label: name,
  };
}

function axisFor(context, subject) {
  const { typescript, checker, displayPathFor } = context;
  const valueType = checker.getTypeAtLocation(subject);
  const valueName = namedType(valueType, displayPathFor);

  if (valueName !== undefined) return valueName;

  if (typescript.isPropertyAccessExpression(subject)) {
    const ownerType = checker.getTypeAtLocation(subject.expression);
    const ownerName = namedType(ownerType, displayPathFor);

    if (ownerName !== undefined) {
      return {
        key: `${ownerName.key}.${subject.name.text}`,
        label: `${ownerName.label}.${subject.name.text}`,
      };
    }
  }

  return undefined;
}

function siteKeyOf(displayPathFor, site) {
  const start = site.scope.getStart(site.sourceFile);

  return `${displayPathFor(site.sourceFile)}:${start}`;
}

function scatteredReports(context) {
  const { sites, displayPathFor, maximumVariants } = context;
  const axes = new Map();

  for (const site of sites) {
    const axis = axisFor(context, site.subject);

    if (axis === undefined) continue;

    const group = axes.get(axis.key) ?? {
      label: axis.label,
      sites: new Map(),
      variants: new Set(),
    };
    const siteKey = `${displayPathFor(site.sourceFile)}:${site.scope.pos}`;

    if (!group.sites.has(siteKey)) group.sites.set(siteKey, site);

    for (const variant of site.variants) group.variants.add(variant);

    axes.set(axis.key, group);
  }

  const reports = [];

  for (const group of axes.values()) {
    const sites = [...group.sites.values()];
    const paths = new Set(
      sites.map((site) => displayPathFor(site.sourceFile)),
    );
    const exceedsThreshold =
      sites.length > 1 && group.variants.size > maximumVariants;

    if (paths.size < 2 || !exceedsThreshold) {
      continue;
    }

    const first = sites.sort((left, right) => {
      const leftKey = siteKeyOf(displayPathFor, left);
      const rightKey = siteKeyOf(displayPathFor, right);
      return leftKey.localeCompare(rightKey);
    })[0];
    const start = first.sourceFile.getLineAndCharacterOfPosition(
      first.scope.getStart(first.sourceFile),
    );
    const variants = [...group.variants].sort();
    const firstPath = displayPathFor(first.sourceFile);
    reports.push(
      `${firstPath}:${start.line + 1}: ${group.label} dispatch ` +
        `is scattered across ${sites.length} functions in ${paths.size} ` +
        `files: ${variants.join(", ")}`,
    );
  }

  return reports;
}

module.exports = { namedType, scatteredReports };
