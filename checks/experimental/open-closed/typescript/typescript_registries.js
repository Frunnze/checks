const {
  recordArguments,
  literalDomain,
  domainKey,
  containsCallable,
  objectDomain,
  descriptorArray,
  aliasesByDomain,
  objectContainsBehavior,
} = require("./registry_values");

const SHARED_MAJORITY = 2;

function registriesIn(
  typescript,
  checker,
  sourceFiles,
  displayPathFor,
  namedType,
) {
  const found = [];
  const aliases = aliasesByDomain(typescript, checker, sourceFiles);

  function add(sourceFile, node, domain, key, isBehavior) {
    const aliasesForDomain = aliases.get(domainKey(domain)) ?? [];
    const inferredKey =
      key ??
      (aliasesForDomain.length === 0
        ? undefined
        : {
            key: `domain::${domainKey(domain)}`,
            label: [...aliasesForDomain].sort()[0],
          });

    found.push({
      key: inferredKey,
      domain,
      name: node.name.text,
      sourceFile,
      path: displayPathFor(sourceFile),
      position: node.getStart(sourceFile),
      isBehavior,
    });
  }

  function inspect(sourceFile, node) {
    if (
      typescript.isIdentifier(node.name) &&
      node.initializer !== undefined
    ) {
      const typeArguments =
        node.type === undefined
          ? undefined
          : recordArguments(typescript, node.type);

      if (typeArguments !== undefined) {
        const keyType = checker.getTypeFromTypeNode(typeArguments[0]);
        const domain = literalDomain(typescript, keyType);

        if (domain !== undefined) {
          const valueType = checker.getTypeFromTypeNode(typeArguments[1]);
          add(
            sourceFile,
            node,
            domain,
            namedType(keyType),
            containsCallable(checker, valueType, typeArguments[1]),
          );
        }
      } else {
        const objectKeys = objectDomain(typescript, checker, node.initializer);
        const descriptor = descriptorArray(
          typescript,
          checker,
          node.initializer,
        );

        if (objectKeys !== undefined) {
          add(
            sourceFile,
            node,
            objectKeys,
            undefined,
            objectContainsBehavior(
              typescript,
              checker,
              node.initializer,
            ),
          );
        } else if (descriptor !== undefined) {
          add(
            sourceFile,
            node,
            descriptor.domain,
            undefined,
            descriptor.isBehavior,
          );
        }
      }
    }
  }

  for (const sourceFile of sourceFiles) {
    for (const statement of sourceFile.statements) {
      if (!typescript.isVariableStatement(statement)) continue;

      for (const declaration of statement.declarationList.declarations) {
        inspect(sourceFile, declaration);
      }
    }
  }

  return found;
}

function labelFor(group) {
  const labels = group
    .map((registry) => registry.key?.label)
    .filter((label) => label !== undefined)
    .sort();

  return labels[0] ?? "variant";
}

function namedDifferently(narrow, wide) {
  return (
    narrow.key !== undefined &&
    wide.key !== undefined &&
    narrow.key.key !== wide.key.key
  );
}

function sameAxis(narrow, wide) {
  if (domainKey(narrow.domain) === domainKey(wide.domain)) return true;
  if (namedDifferently(narrow, wide)) return false;

  return (
    isSubset(narrow.domain, wide.domain) &&
    narrow.domain.size * SHARED_MAJORITY > wide.domain.size
  );
}

function groupedByAxis(registries) {
  const widestFirst = [...registries].sort((left, right) => {
    const bySize = right.domain.size - left.domain.size;

    return bySize === 0
      ? domainKey(left.domain).localeCompare(domainKey(right.domain))
      : bySize;
  });
  const groups = [];

  for (const registry of widestFirst) {
    const covering = groups.find((group) =>
      group.every((member) => sameAxis(registry, member)),
    );

    if (covering === undefined) {
      groups.push([registry]);
    } else {
      covering.push(registry);
    }
  }

  return groups;
}

function repeatedRegistryReports(registries) {
  const reports = [];

  for (const group of groupedByAxis(registries)) {
    const shared = Math.min(...group.map((entry) => entry.domain.size));
    const enoughRegistries =
      group.length >= 3 || (group.length >= 2 && shared >= 3);

    if (!enoughRegistries) continue;

    const ordered = [...group].sort((left, right) => {
      const pathOrder = left.path.localeCompare(right.path);

      return pathOrder === 0 ? left.position - right.position : pathOrder;
    });
    const first = ordered[0];
    const start = first.sourceFile.getLineAndCharacterOfPosition(first.position);
    const names = ordered.map((registry) => registry.name).sort();
    const paths = new Set(group.map((registry) => registry.path));
    reports.push(
      `${first.path}:${start.line + 1}: ${labelFor(group)} behavior is split ` +
        `across ${group.length} registries in ${paths.size} ` +
        `${paths.size === 1 ? "file" : "files"}: ${names.join(", ")}`,
    );
  }

  return reports;
}

function isSubset(left, right) {
  return [...left].every((value) => right.has(value));
}

function registryReports(context) {
  const registries = registriesIn(
    context.typescript,
    context.checker,
    context.sourceFiles,
    context.displayPathFor,
    context.namedType,
  );

  return repeatedRegistryReports(registries);
}

module.exports = { registryReports };
