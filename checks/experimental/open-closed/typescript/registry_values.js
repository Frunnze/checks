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

function propertyName(typescript, checker, node) {
  if (
    typescript.isIdentifier(node) ||
    typescript.isStringLiteral(node) ||
    typescript.isNumericLiteral(node)
  ) {
    return node.text;
  }
  if (typescript.isComputedPropertyName(node)) {
    const keyType = checker.getTypeAtLocation(node.expression);

    return keyType.isStringLiteral() ? keyType.value : undefined;
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

function objectDomain(typescript, checker, initializer) {
  const object = unwrappedInitializer(typescript, initializer);

  if (!typescript.isObjectLiteralExpression(object)) return undefined;

  const domain = new Set();

  for (const property of object.properties) {
    if (
      !typescript.isPropertyAssignment(property) &&
      !typescript.isShorthandPropertyAssignment(property) &&
      !typescript.isMethodDeclaration(property)
    ) {
      return undefined;
    }

    const name = propertyName(typescript, checker, property.name);

    if (name === undefined) return undefined;

    domain.add(name);
  }

  return domain.size >= 3 ? domain : undefined;
}

function descriptorArray(typescript, checker, initializer) {
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
    .map((property) => propertyName(typescript, checker, property.name))
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
          propertyName(typescript, checker, entry.name) === candidate,
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

module.exports = {
  recordArguments,
  literalDomain,
  domainKey,
  containsCallable,
  objectDomain,
  descriptorArray,
  aliasesByDomain,
  objectContainsBehavior,
  stringValue,
};
