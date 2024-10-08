import globals from "globals";
// import path from "node:path";
// import { fileURLToPath } from "node:url";
import js from "@eslint/js";
// import { FlatCompat } from "@eslint/eslintrc";
import jsdoc from 'eslint-plugin-jsdoc';

// const __filename = fileURLToPath(import.meta.url);
// const __dirname = path.dirname(__filename);
// const compat = new FlatCompat({
//     baseDirectory: __dirname,
//     recommendedConfig: js.configs.recommended,
//     allConfig: js.configs.all
// });

export default [
    js.configs.all,
    jsdoc.configs['flat/recommended'],
    // ...compat.extends("google"),
    {
        languageOptions: {
            globals: {
                ...globals.browser,
            },
            ecmaVersion: "latest",
            sourceType: "script",
        },
        settings: { "jsdoc": {"mode": "jsdoc"}, },
        rules: {
            "func-style": "off", // Since I have one file, I don't need to worry about how I declare my functions
            "id-length": "off", // I'm happy with the few one letter variables I have
            indent: ["error", 4],
            "max-len": ["error", {code: 120}], // The PyCharm Python default
            "max-lines": "off", // Default is 300
            "max-params": ["error", {max: 4}], // Default is 3
            "max-statements": "off", // Default is 10.  I have up to 23
            "no-implicit-globals": "off", // Since I have one file, I don't need to worry about how I declare my functions
            "no-inline-comments": "off", // They can be useful
            "no-loop-func": "off", // See getLogisticBestFitRate
            "no-magic-numbers": "off", // I'm happy with the magic numbers I have
            "no-ternary": "off", // Sometimes useful
            "no-use-before-define": ["error", {functions: false}],
            "one-var": ["error", "consecutive"],
            "operator-linebreak": ["error", "before"], // Operators should be at the beginning of lines
            "sort-keys": "off", // Different order can be useful
            "sort-vars": "off", // Different order can be useful, and sometimes necessary
            strict: "off", // Since I have one file, I don't need to worry about how I declare my functions
            yoda: ["error", "never", {onlyEquality: true}], // I would prefer exceptRange, but that gives false positives
            // jsdoc rules
            "jsdoc/multiline-blocks": ["warn", {"noZeroLineText": false, "noFinalLineText": false}],
            "jsdoc/require-returns-description": "off",
            "jsdoc/require-param-description": "off",
            "jsdoc/no-multi-asterisks": "off", // Should not be necessary?
            "jsdoc/check-syntax": "error",
            "jsdoc/check-template-names": "error",
            "jsdoc/informative-docs": "warn",
            "jsdoc/match-description": "warn",
            "jsdoc/no-bad-blocks": "warn",
            "jsdoc/no-blank-block-descriptions": "warn",
            "jsdoc/no-defaults": "warn",
            "jsdoc/require-asterisk-prefix": "error",
            "jsdoc/require-file-overview": "error",
            "jsdoc/require-hyphen-before-param-description": "warn",
            "jsdoc/require-throws": "warn",
            "jsdoc/sort-tags": "warn",
        },
    }
];