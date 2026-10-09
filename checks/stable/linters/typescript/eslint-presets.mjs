import eslint from "@eslint/js";
import typescriptEslint from "typescript-eslint";

import solidPreset from "eslint-plugin-solid/configs/typescript";

export const presets = { solid: solidPreset };

const SHARED_RULES = {
  "@typescript-eslint/consistent-type-definitions": ["error", "type"],
  "@typescript-eslint/dot-notation": [
    "error",
    { allowIndexSignaturePropertyAccess: true },
  ],
  "@typescript-eslint/no-extraneous-class": "off",
  "@typescript-eslint/restrict-template-expressions": [
    "error",
    { allowNumber: true },
  ],
  "@typescript-eslint/unbound-method": ["error", { ignoreStatic: true }],
};

export function typescriptConfigFor(packageDirectory, extraPresets = []) {
  return typescriptEslint.config(
    eslint.configs.recommended,
    typescriptEslint.configs.strictTypeChecked,
    typescriptEslint.configs.stylisticTypeChecked,
    ...extraPresets,
    {
      languageOptions: {
        parserOptions: {
          projectService: true,
          tsconfigRootDir: packageDirectory,
        },
      },
      rules: SHARED_RULES,
    },
  );
}
