const fs = require("fs");
const path = require("path");
const { registryReports } = require("./typescript_registries");
const { factoryReports } = require("./typescript_factories");
const { enumReports } = require("./typescript_enums");

const MAXIMUM_VARIANTS = 2;
const typescript = require(process.argv[2]);
let displayPaths = new Map();

function displayPathFor(sourceFile) {
  return displayPaths.get(path.resolve(sourceFile.fileName)) ?? sourceFile.fileName;
}

function isFunctionScope(node) {
  return (
    typescript.isFunctionDeclaration(node) ||
    typescript.isFunctionExpression(node) ||
    typescript.isArrowFunction(node) ||
    typescript.isMethodDeclaration(node) ||
    typescript.isConstructorDeclaration(node) ||
    typescript.isGetAccessorDeclaration(node) ||
    typescript.isSetAccessorDeclaration(node)
  );
}

function stringFrom(node) {
  if (
    typescript.isStringLiteral(node) ||
    typescript.isNoSubstitutionTemplateLiteral(node)
  ) {
    return node.text;
  }

  return undefined;
}

function unwrapped(node) {
  let current = node;

  while (typescript.isParenthesizedExpression(current)) {
    current = current.expression;
  }

  return current;
}

function comparisonFrom(node) {
  if (!typescript.isBinaryExpression(node)) return undefined;

  const comparisons = new Set([
    typescript.SyntaxKind.EqualsEqualsToken,
    typescript.SyntaxKind.EqualsEqualsEqualsToken,
    typescript.SyntaxKind.ExclamationEqualsToken,
    typescript.SyntaxKind.ExclamationEqualsEqualsToken,
  ]);

  if (!comparisons.has(node.operatorToken.kind)) return undefined;

  const leftString = stringFrom(node.left);
  const rightString = stringFrom(node.right);

  if (leftString !== undefined && rightString === undefined) {
    return { subject: unwrapped(node.right), variant: leftString };
  }
  if (rightString !== undefined && leftString === undefined) {
    return { subject: unwrapped(node.left), variant: rightString };
  }

  return undefined;
}

function membershipFrom(node) {
  if (!typescript.isCallExpression(node)) return undefined;
  if (node.arguments.length !== 1) return undefined;

  const callee = node.expression;

  if (!typescript.isPropertyAccessExpression(callee)) return undefined;
  if (callee.name.text !== "includes") return undefined;

  const array = unwrapped(callee.expression);

  if (!typescript.isArrayLiteralExpression(array)) return undefined;

  const variants = array.elements.map(stringFrom);

  if (variants.length === 0) return undefined;
  if (variants.some((variant) => variant === undefined)) return undefined;

  return { subject: unwrapped(node.arguments[0]), variants };
}

function record(groups, sourceFile, subject, variant) {
  if (typescript.isTypeOfExpression(subject)) return;

  const display = subject.getText(sourceFile).replace(/\s+/g, "");
  const group = groups.get(display) ?? { subject, variants: new Set() };
  group.variants.add(variant);
  groups.set(display, group);
}

function collectFrom(sourceFile, root) {
  const groups = new Map();

  function visit(node) {
    if (node !== root && isFunctionScope(node)) return;
    if (
      node !== root &&
      (typescript.isClassDeclaration(node) ||
        typescript.isClassExpression(node))
    ) {
      return;
    }

    const comparison = comparisonFrom(node);

    if (comparison !== undefined) {
      record(groups, sourceFile, comparison.subject, comparison.variant);
    }

    const membership = membershipFrom(node);

    if (membership !== undefined) {
      for (const variant of membership.variants) {
        record(groups, sourceFile, membership.subject, variant);
      }
    }

    if (typescript.isSwitchStatement(node)) {
      for (const clause of node.caseBlock.clauses) {
        if (!typescript.isCaseClause(clause)) continue;

        const variant = stringFrom(clause.expression);

        if (variant !== undefined) {
          record(groups, sourceFile, unwrapped(node.expression), variant);
        }
      }
    }

    typescript.forEachChild(node, visit);
  }

  visit(root);
  return groups;
}

function nameOf(sourceFile, node) {
  if (node.name !== undefined) return node.name.getText(sourceFile);

  if (
    (typescript.isArrowFunction(node) ||
      typescript.isFunctionExpression(node)) &&
    node.parent !== undefined &&
    typescript.isVariableDeclaration(node.parent)
  ) {
    return node.parent.name.getText(sourceFile);
  }

  if (typescript.isConstructorDeclaration(node)) return "constructor";

  return "(anonymous)";
}

function reportFor(sourceFile, scope, subject, variants) {
  const start = sourceFile.getLineAndCharacterOfPosition(
    scope.getStart(sourceFile),
  );
  const values = [...variants].sort();

  return (
    `${displayPathFor(sourceFile)}:${start.line + 1}: ${nameOf(sourceFile, scope)} compares ` +
    `${subject} to ${values.length} strings: ${values.join(", ")}`
  );
}

function dispatchSitesIn(sourceFile) {
  const found = [];

  function visit(node) {
    if (isFunctionScope(node)) {
      for (const [display, group] of collectFrom(sourceFile, node)) {
        found.push({
          sourceFile,
          scope: node,
          subject: group.subject,
          display,
          variants: group.variants,
        });
      }
    }

    typescript.forEachChild(node, visit);
  }

  visit(sourceFile);
  return found;
}

function namedType(type) {
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

function axisFor(checker, subject) {
  const valueType = checker.getTypeAtLocation(subject);
  const valueName = namedType(valueType);

  if (valueName !== undefined) return valueName;

  if (typescript.isPropertyAccessExpression(subject)) {
    const ownerType = checker.getTypeAtLocation(subject.expression);
    const ownerName = namedType(ownerType);

    if (ownerName !== undefined) {
      return {
        key: `${ownerName.key}.${subject.name.text}`,
        label: `${ownerName.label}.${subject.name.text}`,
      };
    }
  }

  return undefined;
}

function scatteredReports(checker, sites) {
  const axes = new Map();

  for (const site of sites) {
    const axis = axisFor(checker, site.subject);

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
      sites.length > 1 && group.variants.size > MAXIMUM_VARIANTS;

    if (paths.size < 2 || !exceedsThreshold) {
      continue;
    }

    const first = sites.sort((left, right) => {
      const leftKey = `${displayPathFor(left.sourceFile)}:${left.scope.getStart(left.sourceFile)}`;
      const rightKey = `${displayPathFor(right.sourceFile)}:${right.scope.getStart(right.sourceFile)}`;
      return leftKey.localeCompare(rightKey);
    })[0];
    const start = first.sourceFile.getLineAndCharacterOfPosition(
      first.scope.getStart(first.sourceFile),
    );
    const variants = [...group.variants].sort();
    reports.push(
      `${displayPathFor(first.sourceFile)}:${start.line + 1}: ${group.label} dispatch ` +
        `is scattered across ${sites.length} functions in ${paths.size} ` +
        `files: ${variants.join(", ")}`,
    );
  }

  return reports;
}

function localReports(sites) {
  const found = [];

  for (const site of sites) {
    if (site.variants.size > MAXIMUM_VARIANTS) {
      found.push(
        reportFor(
          site.sourceFile,
          site.scope,
          site.display,
          site.variants,
        ),
      );
    }
  }

  return found;
}

function programFor(paths) {
  return typescript.createProgram(paths, {
    target: typescript.ScriptTarget.Latest,
    module: typescript.ModuleKind.ESNext,
    moduleResolution: typescript.ModuleResolutionKind.Bundler,
    jsx: typescript.JsxEmit.Preserve,
    skipLibCheck: true,
    noEmit: true,
  });
}

const paths = fs.readFileSync(0, "utf8").split(/\s+/).filter(Boolean);
displayPaths = new Map(paths.map((filePath) => [path.resolve(filePath), filePath]));
const rootPaths = [...displayPaths.keys()];
const program = programFor(rootPaths);
const pathSet = new Set(rootPaths);
const sourceFiles = program
  .getSourceFiles()
  .filter((sourceFile) => pathSet.has(path.resolve(sourceFile.fileName)));
const checker = program.getTypeChecker();
const sites = sourceFiles.flatMap(dispatchSitesIn);
const reported = [
  ...localReports(sites),
  ...scatteredReports(checker, sites),
  ...registryReports({
    typescript,
    checker,
    sourceFiles,
    displayPathFor,
    namedType,
  }),
  ...factoryReports({
    typescript,
    sourceFiles,
    displayPathFor,
  }),
  ...enumReports({
    typescript,
    checker,
    sourceFiles,
    displayPathFor,
    isFunctionScope,
    nameOf,
  }),
].sort();

for (const dispatch of reported) process.stdout.write(dispatch + "\n");
