import eslint from "@eslint/js";
import globals from "globals";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "build/**", "coverage/**", "node_modules/**", "playwright-report/**", "test-results/**", "*.min.js"],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  // Accessibility mistakes (unlabelled controls, non-focusable interactive elements, bad alt text)
  // are caught at review time instead of by users. Intentional exceptions carry a reason inline.
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    settings: {
      // Our <Checkbox> renders a Radix <button role="checkbox">, which a wrapping <label> labels
      // natively; tell the rules so they check labels around it like any other control.
      "jsx-a11y": { components: { Checkbox: "input" } },
    },
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // A promise nobody awaits swallows its failure. Mark deliberate fire-and-forget with `void`.
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
    },
  },
);
