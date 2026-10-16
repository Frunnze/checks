from pathlib import Path

import pytest

from check_support import (
    CheckRun,
    link_toolkit_node_modules,
    repository,
    run_configured,
    stage_file,
)

CONFIGURATION = 'source_directories = ["web/src"]\n'
MODULE = "web/src/value.ts"
LOOSE_TSCONFIG = """{
  "compilerOptions": {
    "noEmit": true,
    "target": "es2022",
    "strict": false,
    "noImplicitAny": false,
    "noImplicitThis": false,
    "strictNullChecks": false,
    "strictFunctionTypes": false,
    "strictBindCallApply": false,
    "strictPropertyInitialization": false,
    "strictBuiltinIteratorReturn": false,
    "useUnknownInCatchVariables": false,
    "noUncheckedIndexedAccess": false,
    "exactOptionalPropertyTypes": false,
    "noImplicitOverride": false,
    "noImplicitReturns": false,
    "noFallthroughCasesInSwitch": false,
    "noPropertyAccessFromIndexSignature": false,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "allowUnreachableCode": true,
    "allowUnusedLabels": true,
    "noUncheckedSideEffectImports": false
  },
  "include": ["src"]
}
"""
WELL_TYPED_MODULE = """export function double(amount: number): number {
  return amount * 2;
}
"""
LOOSELY_TYPED_MODULES = {
    "noImplicitAny": """export function double(amount) {
  return amount * 2;
}
""",
    "noImplicitThis": """export const counter = {
  count: 0,
  next: function () {
    return function () {
      return this.count;
    };
  },
};
""",
    "strictNullChecks": """export const label: string = null;
""",
    "strictFunctionTypes": """const measure = (text: string): number => text.length;
export const wide: (text: string | number) => number = measure;
""",
    "strictBindCallApply": """function double(amount: number): number {
  return amount * 2;
}
export const doubled = double.call(undefined, "two");
""",
    "strictPropertyInitialization": """export class Box {
  size: number;
}
""",
    "strictBuiltinIteratorReturn": """const values = [1, 2][Symbol.iterator]();
export const first: number = values.next().value;
""",
    "useUnknownInCatchVariables": """export function message(): string {
  try {
    return "ok";
  } catch (error) {
    return error.message;
  }
}
""",
    "noUncheckedIndexedAccess": """const names: string[] = [];
export const first: string = names[0];
""",
    "exactOptionalPropertyTypes": """type Person = { nickname?: string };
export const person: Person = { nickname: undefined };
""",
    "noImplicitOverride": """class Greeter {
  greet(): string {
    return "hi";
  }
}
export class LoudGreeter extends Greeter {
  greet(): string {
    return "HI";
  }
}
""",
    "noImplicitReturns": """export function sign(amount: number) {
  if (amount > 0) {
    return 1;
  }
}
""",
    "noFallthroughCasesInSwitch": """export function name(amount: number): string {
  let text = "";
  switch (amount) {
    case 1:
      text = "one";
    case 2:
      text = "two";
      break;
  }
  return text;
}
""",
    "noPropertyAccessFromIndexSignature": """const counts: Record<string, number> = {};
export const total = counts.total;
""",
    "noUnusedLocals": """const unused = 1;
export const value = 2;
""",
    "noUnusedParameters": """export function first(left: number, right: number): number {
  return left;
}
""",
    "allowUnreachableCode": """export function value(): number {
  return 1;
  return 2;
}
""",
    "allowUnusedLabels": """export function loop(): void {
  unused: for (;;) {
    break;
  }
}
""",
    "noUncheckedSideEffectImports": """import "./missing-module";
export const value = 1;
""",
}


def _type_check(tmp_path: Path, source: str) -> CheckRun:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, MODULE, source)
    stage_file(tmp_path, "web/tsconfig.json", LOOSE_TSCONFIG)
    stage_file(tmp_path, "web/package.json", '{"name": "web"}\n')
    (tmp_path / "web" / "node_modules").mkdir()

    return run_configured(tmp_path, CONFIGURATION, "strict-typing")


@pytest.mark.parametrize(
    "loosely_typed_module",
    LOOSELY_TYPED_MODULES.values(),
    ids=LOOSELY_TYPED_MODULES.keys(),
)
def test_fails_on_code_only_a_loose_tsconfig_accepts(
    tmp_path: Path, loosely_typed_module: str
) -> None:
    finished = _type_check(tmp_path, loosely_typed_module)

    assert finished.returncode == 1, finished.stdout
    assert "web does not type-check" in finished.stderr


def test_passes_well_typed_code_under_a_loose_tsconfig(
    tmp_path: Path,
) -> None:
    finished = _type_check(tmp_path, WELL_TYPED_MODULE)

    assert finished.returncode == 0, finished.stdout + finished.stderr
