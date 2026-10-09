# checks

Static-analysis checks for Python, TypeScript and PHP that any repository can
run without carrying them. A repository keeps exactly one file, `checks.toml`,
that says which folders to check, which checks to run, when to run them, their
settings and their whitelists. The toolkit sees the language of each folder and
runs the matching checks.

## Use it in a repository

1. Put `checks.toml` at the root of the repository (one file, even with many
   services). The smallest one runs every stable check on pre-commit:

   ```toml
   source_directories = ["user-service/src", "ui-service/src"]
   ```

2. Clone the toolkit into `.checks/` and install it. `install.sh` installs the
   tools, points the repository's git hooks at `.checks/hooks` and adds
   `.checks/` to `.gitignore`:

   ```sh
   git clone https://github.com/Frunnze/checks .checks
   .checks/install.sh
   ```

3. Commit. The `pre-commit` and `pre-push` hooks run the checks `checks.toml`
   assigns to them. Run them by hand with `.checks/run`, or one check with
   `.checks/run linters`.

`install.sh` needs `python3` (3.12+), `node`, `composer` for PHP, and
`gitleaks` (`brew install gitleaks`). The repository installs its own
dependencies (its `.venv`, `node_modules`, `vendor`) as usual: coverage, type
checking and dependency audits read them.

Each source folder must be named `src`, with its tests in a sibling `tests`
folder (`user-service/src`, `user-service/tests`). A folder holding no Python,
TypeScript or PHP fails the run, and code in an unsupported language (`.js`,
`.go`, ...) is reported as unchecked.

## Use it in GitHub Actions

In the other repository's workflow, install that repository's dependencies,
then call the toolkit as an action. It installs its own tools and runs every
enabled check over the whole repository:

```yaml
name: checks
on: [push, pull_request]

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: composer install --working-dir=api
      - run: npm ci --prefix ui
      - uses: Frunnze/checks@main
```

`fetch-depth: 0` lets the secrets check scan the full history. The action
takes one input, `stage` (default `ci`): `pre-commit` or `pre-push` run only
the checks assigned to that hook.

## Checks

Every stable check runs at the hook `stable` names (`pre-commit` by default).
An experimental check runs only when `checks.toml` gives it a `when`. Secrets
and file length check every language at once; every other check has one folder
per language.

| Check | Stability | Python | TypeScript | PHP | Whitelist entry |
| --- | --- | --- | --- | --- | --- |
| `secrets` | stable | gitleaks | gitleaks | gitleaks | gitleaks finding fingerprint |
| `file-length` | stable | max lines | max lines | max lines | text of the finding, usually the path |
| `duplicate-code` | stable | jscpd | jscpd | jscpd | glob of files to ignore |
| `dead-code` | stable | vulture | knip | phpstan + shipmonk dead code | vulture name (Python) |
| `linters` | stable | ruff, pylint | eslint strictTypeChecked | phpcs | `ruff:CODE`, `pylint:name`, `eslint:rule`, `phpcs:Sniff` |
| `unused-deps` | stable | deptry | knip | composer-dependency-analyser | none |
| `vulnerable-deps` | stable | pip-audit | npm audit | composer audit | advisory id |
| `security-patterns` | stable | semgrep | semgrep | semgrep | semgrep rule id |
| `strict-typing` | stable | basedpyright | tsc | phpstan level max, strict rules | folder PHPStan skips (PHP), e.g. fake WordPress in tests |
| `coverage` | stable | pytest-cov (branch) | the package's `coverage` script | phpunit | none |
| `single-responsibility` | experimental | yes | yes | - | finding table (see below) |
| `feature-isolation` | experimental | yes | yes | yes | text of the finding |
| `open-closed` | experimental | yes | yes | - | text of the finding |
| `dependency-inversion` | experimental | yes | - | - | text of the finding |
| `definition-names` | experimental | yes | yes | - | text of the finding |
| `nested-definitions` | experimental | yes | yes | - | text of the finding |
| `property-tests` | experimental | hypothesis | fast-check | eris | text of the finding |
| `api-contract` | experimental | schemathesis test | - | - | none |

`feature-isolation` fails when a checked folder does not follow the layout:
`src/features/<feature>/...` (`src/Features/` in PHP) with an optional `shared`
folder beside it.

## checks.toml

One section per check, each with the same three settings, plus the check's own
options. A section overrides the defaults for that check only.

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
whitelist = ["api/src/generated/schema.py"]

[checks.open-closed]
when = "pre-push"

[checks.vulnerable-deps]
whitelist = ["GHSA-vfj7-8cjw-p6xm"]
```

| Setting | Values | Default |
| --- | --- | --- |
| `source_directories` | folders named `src` | required at the top; a check may narrow it |
| `stable` | `pre-commit`, `pre-push`, `both`, `off` | `pre-commit` |
| `python_environment` | the repository's virtual environment | `.venv` |
| `when` | `pre-commit`, `pre-push`, `both`, `off` | `stable` for a stable check, `off` for an experimental one |
| `scope` | `repository`, or `changed`: staged files on pre-commit, unpushed commits on pre-push | `repository` |
| `whitelist` | entries as the checks table describes | none |
| `max-lines` | `file-length` only | 300 |
| `fail-under` | `coverage` only | 100 |

With `scope = "changed"` a check runs only on folders with changes, and the
toolkit's own finders report only findings in changed files.

The tools keep their own option names under their check, layered over the
toolkit's defaults - only when a repository needs to differ:

```toml
[checks.linters.ruff]
line-length = 100

[checks.linters.eslint]
presets = ["solid"]
rules = { "@typescript-eslint/consistent-type-definitions" = "off" }

[checks.linters.phpcs]
standard = "PSR12"

[checks.strict-typing.phpstan]
parameters = { level = 8 }

[checks.unused-deps.composer-dependency-analyser]
ignore-errors = ["UNKNOWN_CLASS"]
```

A PHP package whose `composer.json` has `"type": "wordpress-plugin"` gets the
WordPress coding standards, the WordPress PHPStan extension and WordPress
classes in the dependency check without any setting
(`configuration/frameworks/wordpress.toml`). Python type checking reads the
package's own `[tool.basedpyright]`, because it needs the package's import
paths.

## Layout

```
run                       runs the enabled checks (--stage pre-commit|pre-push|ci)
install.sh                installs the tools and wires the git hooks
hooks/                    the git hooks a repository points core.hooksPath at
action.yml                the GitHub action
tools.sh                  helpers every check script sources
configuration/            reads checks.toml and writes the tools' configs
checks/stable/<check>/<language>/check
checks/experimental/<check>/<language>/check
tests/<check>/            the toolkit's own tests
```

A new language is a new `<language>` folder in each check plus a
`<language>_files_in` helper in `tools.sh`.

## Develop the toolkit

```sh
./install.sh
.venv/bin/python -m pytest tests
```
