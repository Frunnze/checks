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
  const typeArguments = (type.aliasTypeArguments ?? []).map((argument) =>
    namedType(argument, displayPathFor),
  );

  if (typeArguments.some((argument) => argument === undefined)) {
    return undefined;
  }
  if (typeArguments.length === 0) {
    return {
      key: `${declarationPath}::${name}`,
      label: name,
    };
  }

  const argumentKeys = typeArguments.map((argument) => argument.key);
  const argumentLabels = typeArguments.map((argument) => argument.label);

  return {
    key: `${declarationPath}::${name}<${argumentKeys.join(", ")}>`,
    label: `${name}<${argumentLabels.join(", ")}>`,
  };
}

function memberOf(typescript, checker, subject) {
  if (typescript.isPropertyAccessExpression(subject)) {
    return { owner: subject.expression, name: subject.name.text };
  }
  if (!typescript.isIdentifier(subject)) return undefined;

  const declaration = checker.getSymbolAtLocation(subject)?.valueDeclaration;

  if (declaration === undefined) return undefined;
  if (!typescript.isBindingElement(declaration)) return undefined;
  if (!typescript.isObjectBindingPattern(declaration.parent)) return undefined;

  const property = declaration.propertyName ?? declaration.name;

  if (!typescript.isIdentifier(property)) return undefined;

  return { owner: declaration.parent, name: property.text };
}

function axisFor(context, subject) {
  const { typescript, checker, displayPathFor } = context;
  const valueType = checker.getTypeAtLocation(subject);
  const valueName = namedType(valueType, displayPathFor);

  if (valueName !== undefined) return valueName;

  const member = memberOf(typescript, checker, subject);

  if (member !== undefined) {
    const ownerType = checker.getTypeAtLocation(member.owner);
    const ownerName = namedType(ownerType, displayPathFor);

    if (ownerName !== undefined) {
      return {
        key: `${ownerName.key}.${member.name}`,
        label: `${ownerName.label}.${member.name}`,
      };
    }
  }

  return undefined;
}

function startOf(site) {
  return site.scope.getStart(site.sourceFile);
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

    const firstByPath = new Map();

    for (const site of sites) {
      const sitePath = displayPathFor(site.sourceFile);
      const known = firstByPath.get(sitePath);

      if (known === undefined || startOf(site) < startOf(known)) {
        firstByPath.set(sitePath, site);
      }
    }

    const variants = [...group.variants].sort();

    for (const [firstPath, first] of firstByPath) {
      const start = first.sourceFile.getLineAndCharacterOfPosition(
        startOf(first),
      );
      reports.push(
        `${firstPath}:${start.line + 1}: ${group.label} dispatch ` +
          `is scattered across ${sites.length} functions in ${paths.size} ` +
          `files: ${variants.join(", ")}`,
      );
    }
  }

  return reports;
}

module.exports = { namedType, scatteredReports };
