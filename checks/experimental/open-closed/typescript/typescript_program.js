const path = require("path");

const NO_INPUTS_FOUND = 18003;

function failOnDiagnostics(typescript, config, diagnostics) {
  const fatal = diagnostics.filter(
    (diagnostic) => diagnostic.code !== NO_INPUTS_FOUND,
  );

  if (fatal.length === 0) return;

  const message = typescript.flattenDiagnosticMessageText(
    fatal[0].messageText,
    " ",
  );

  throw new Error(`${config}: ${message}`);
}

function configuredOptions(typescript, config) {
  const read = typescript.readConfigFile(config, typescript.sys.readFile);
  const readErrors = read.error === undefined ? [] : [read.error];

  failOnDiagnostics(typescript, config, readErrors);

  const parsed = typescript.parseJsonConfigFileContent(
    read.config,
    typescript.sys,
    path.dirname(config),
    undefined,
    config,
  );

  failOnDiagnostics(typescript, config, parsed.errors);

  return parsed.options;
}

function projectOptionsByFile(typescript, paths) {
  const byConfig = new Map();
  const byFile = new Map();

  for (const filePath of paths) {
    const config = typescript.findConfigFile(
      path.dirname(filePath),
      typescript.sys.fileExists,
    );

    if (config === undefined) continue;
    if (!byConfig.has(config)) {
      byConfig.set(config, configuredOptions(typescript, config));
    }

    byFile.set(filePath, byConfig.get(config));
  }

  return byFile;
}

function programFor(typescript, paths) {
  const options = {
    target: typescript.ScriptTarget.Latest,
    module: typescript.ModuleKind.ESNext,
    moduleResolution: typescript.ModuleResolutionKind.Bundler,
    jsx: typescript.JsxEmit.Preserve,
    skipLibCheck: true,
    noEmit: true,
  };
  const projectOptions = projectOptionsByFile(typescript, paths);
  const host = typescript.createCompilerHost(options);

  host.resolveModuleNameLiterals = (literals, containingFile) => {
    const resolution =
      projectOptions.get(path.resolve(containingFile)) ?? options;

    return literals.map((literal) =>
      typescript.resolveModuleName(
        literal.text,
        containingFile,
        resolution,
        host,
      ),
    );
  };

  return typescript.createProgram(paths, options, host);
}

module.exports = { programFor };
