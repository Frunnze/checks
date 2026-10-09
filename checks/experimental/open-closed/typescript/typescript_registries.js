const SHARED_MAJORITY = 2;

function typeReferenceNamed(typescript, node, name) {
  return (
    typescript.isTypeReferenceNode(node) &&
    node.typeName.getText() === name
  );
}

function recordArguments(typescript, node) {
  let current = node;

  if (typeReferenceNamed(typescript, current, "Readonly")) {
    const wrapped = current.typeArguments?.[0];

    if (wrapped === undefined) return undefined;

    current = wrapped;
  }

  if (!typeReferenceNamed(typescript, current, "Record")) return undefined;
  if (current.typeArguments?.length !== 2) return undefined;

  return current.typeArguments;
}

function literalDomain(typescript, type) {
  const values = new Set();
  const members = type.isUnion() ? type.types : [type];

  for (const member of members) {
    if ((member.flags & typescript.TypeFlags.StringLiteral) === 0) {
      return undefined;
    }

    values.add(member.value);
  }

  return values.size >= 2 ? values : undefined;
}

function domainKey(domain) {
  return [...domain].sort().join("\u0000");
}

function containsCallable(checker, type, location, depth = 1) {
  if (type.getCallSignatures().length > 0) return true;
  if (depth <= 0) return false;

  return type.getProperties().some((property) => {
    const propertyType = checker.getTypeOfSymbolAtLocation(property, location);

    return containsCallable(checker, propertyType, location, depth - 1);
  });
}

function unwrappedInitializer(typescript, node) {
  let current = node;

  while (
    typescript.isAsExpression(current) ||
    typescript.isSatisfiesExpression(current) ||
    typescript.isParenthesizedExpression(current)
  ) {
    current = current.expression;
  }

  return current;
}

function propertyName(typescript, node) {
  if (
    typescript.isIdentifier(node) ||
    typescript.isStringLiteral(node) ||
    typescript.isNumericLiteral(node)
  ) {
    return node.text;
  }

  return undefined;
}

function stringValue(typescript, node) {
  const value = unwrappedInitializer(typescript, node);

  if (
    typescript.isStringLiteral(value) ||
    typescript.isNoSubstitutionTemplateLiteral(value)
  ) {
    return value.text;
  }

  return undefined;
}

function objectDomain(typescript, initializer) {
  const object = unwrappedInitializer(typescript, initializer);

  if (!typescript.isObjectLiteralExpression(object)) return undefined;

  const domain = new Set();

  for (const property of object.properties) {
    if (
      !typescript.isPropertyAssignment(property) &&
      !typescript.isMethodDeclaration(property)
    ) {
      return undefined;
    }

    const name = propertyName(typescript, property.name);

    if (name === undefined) return undefined;

    domain.add(name);
  }

  return domain.size >= 3 ? domain : undefined;
}

function descriptorArray(typescript, initializer) {
  const array = unwrappedInitializer(typescript, initializer);

  if (!typescript.isArrayLiteralExpression(array) || array.elements.length < 3) {
    return undefined;
  }

  const stringItems = array.elements.map((element) =>
    stringValue(typescript, element),
  );

  if (stringItems.every((value) => value !== undefined)) {
    return {
      domain: new Set(stringItems),
      isBehavior: false,
    };
  }

  const objects = array.elements.map((element) =>
    unwrappedInitializer(typescript, element),
  );

  if (!objects.every((element) => typescript.isObjectLiteralExpression(element))) {
    return undefined;
  }

  const first = objects[0];
  const candidateNames = first.properties
    .filter(typescript.isPropertyAssignment)
    .map((property) => propertyName(typescript, property.name))
    .filter((name) => name !== undefined);
  const preferred = [
    "kind",
    "type",
    "name",
    "id",
    "choice",
    "tone",
    "status",
    "scope",
    "variant",
  ];
  const ordered = [
    ...preferred.filter((name) => candidateNames.includes(name)),
    ...candidateNames.filter((name) => !preferred.includes(name)),
  ];

  for (const candidate of ordered) {
    const values = objects.map((object) => {
      const property = object.properties.find(
        (entry) =>
          typescript.isPropertyAssignment(entry) &&
          propertyName(typescript, entry.name) === candidate,
      );

      return property === undefined
        ? undefined
        : stringValue(typescript, property.initializer);
    });

    if (
      values.every((value) => value !== undefined) &&
      new Set(values).size === values.length
    ) {
      return { domain: new Set(values), isBehavior: false };
    }
  }

  return undefined;
}

function aliasesByDomain(typescript, checker, sourceFiles) {
  const aliases = new Map();

  function visit(node) {
    if (typescript.isTypeAliasDeclaration(node)) {
      const domain = literalDomain(
        typescript,
        checker.getTypeFromTypeNode(node.type),
      );

      if (domain !== undefined && domain.size >= 3) {
        const key = domainKey(domain);
        const names = aliases.get(key) ?? [];
        names.push(node.name.text);
        aliases.set(key, names);
      }
    }

    typescript.forEachChild(node, visit);
  }

  for (const sourceFile of sourceFiles) visit(sourceFile);

  return aliases;
}

function objectContainsBehavior(typescript, checker, initializer) {
  const object = unwrappedInitializer(typescript, initializer);

  if (!typescript.isObjectLiteralExpression(object)) return false;

  return object.properties.some((property) => {
    if (!typescript.isPropertyAssignment(property)) {
      return typescript.isMethodDeclaration(property);
    }

    const valueType = checker.getTypeAtLocation(property.initializer);

    return containsCallable(checker, valueType, property.initializer);
  });
}

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

  function visit(sourceFile, node) {
    if (
      typescript.isVariableDeclaration(node) &&
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
        const objectKeys = objectDomain(typescript, node.initializer);
        const descriptor = descriptorArray(typescript, node.initializer);

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

    typescript.forEachChild(node, (child) => visit(sourceFile, child));
  }

  for (const sourceFile of sourceFiles) visit(sourceFile, sourceFile);

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
    const covering = groups.find((group) => sameAxis(registry, group[0]));

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
