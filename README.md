# checks

Static-analysis checks for Python, TypeScript and PHP. A repository keeps one
file, `checks.toml`, and the toolkit runs the checks that match each folder's
language.

## Use it in a repository

1. Add `checks.toml` at the repository root:

   ```toml
   source_directories = ["user-service/src", "ui-service/src"]
   ```

2. Install it (installs the tools, turns the git hooks on, ignores `.checks/`):

   ```sh
   git clone https://github.com/Frunnze/checks .checks
   .checks/install.sh
   ```

3. Commit. Run by hand with `.checks/run`, or one check with
   `.checks/run linters`.

Needs `python3` 3.12+, `node`, `composer` (PHP) and `gitleaks`. Tests are read
from a `tests` folder next to each source folder. Code in an unsupported
language is reported as unchecked.

## Use it in GitHub Actions

```yaml
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: npm ci --prefix ui
      - uses: Frunnze/checks@main
```

Install the repository's own dependencies first. The action runs every
enabled check over the whole repository.

## Checks

| Name | Description | Languages | Tools | Stability | Whitelist entry |
| --- | --- | --- | --- | --- | --- |
| `secrets` | No secret is committed | all | gitleaks | stable | finding fingerprint |
| `file-length` | No file over `max-lines` | all | - | stable | path |
| `duplicate-code` | No copied code | Python, TS, PHP | jscpd | stable | glob |
| `dead-code` | Nothing unreachable | Python, TS, PHP | vulture, knip, phpstan | stable | vulture name |
| `linters` | Style and bug-prone patterns | Python, TS, PHP | ruff, pylint, eslint, phpcs | stable | `tool:rule` |
| `unused-deps` | Declared dependencies match imports | Python, TS, PHP | deptry, knip, composer-dependency-analyser | stable | - |
| `vulnerable-deps` | No dependency with a known advisory | Python, TS, PHP | pip-audit, npm audit, composer audit | stable | advisory id |
| `security-patterns` | No insecure dataflow | Python, TS, PHP | semgrep | stable | rule id |
| `strict-typing` | Strict types, no silencing | Python, TS, PHP | basedpyright, tsc, phpstan | stable | folder (PHP) |
| `coverage` | Every line and branch tested | Python, TS, PHP | pytest-cov, package script, phpunit | stable | - |
| `single-responsibility` | One external reason to change per unit | Python, TS | own finder | experimental | finding table |
| `feature-isolation` | Features meet only in `shared` | Python, TS, PHP | own finder | experimental | finding text |
| `open-closed` | No growing closed dispatch | Python, TS | own finder | experimental | finding text |
| `dependency-inversion` | Collaborators injected, not built | Python | own finder | experimental | finding text |
| `definition-names` | No `and`/`or` in names | Python, TS | own finder | experimental | finding text |
| `nested-definitions` | No function inside a function | Python, TS | own finder | experimental | finding text |
| `property-tests` | A property test per function | Python, TS, PHP | own finder | experimental | finding text |
| `api-contract` | No generated request crashes an endpoint | Python | schemathesis | experimental | - |

## checks.toml

```toml
source_directories = ["api/src", "ui/src"]
stable = "pre-commit"

[checks.coverage]
when = "pre-push"
source_directories = ["api/src"]

[checks.linters]
when = "both"
scope = "changed"
whitelist = ["ruff:S311", "eslint:no-console"]

[checks.file-length]
max-lines = 400

[checks.open-closed]
when = "pre-push"
```

- `stable`: the hook every stable check runs at - `pre-commit` (default),
  `pre-push`, `both` or `off`.
- `[checks.<name>]` overrides one check: `when` (same values; experimental
  checks are `off` until set), `scope` (`repository` or `changed`),
  `whitelist`, `source_directories`, and `max-lines` / `fail-under`.
- Tools take their own options under their check, for example
  `[checks.linters.ruff]`, `[checks.linters.eslint]`, `[checks.linters.phpcs]`,
  `[checks.strict-typing.phpstan]`.
- A PHP package with `"type": "wordpress-plugin"` in `composer.json` gets the
  WordPress rules automatically.

## Develop

```sh
./install.sh
.venv/bin/python -m pytest tests
```

`checks/stable|experimental/<check>/<language>/check` holds each check;
`configuration/` reads `checks.toml`.
