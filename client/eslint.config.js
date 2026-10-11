import js from '@eslint/js';
import pluginQuasar from '@quasar/app-vite/eslint';
import prettierSkipFormatting from '@vue/eslint-config-prettier/skip-formatting';
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript';
import pluginVue from 'eslint-plugin-vue';
import globals from 'globals';

export default defineConfigWithVueTs(
  { ignores: ['dist/**', '.quasar/**'] },
  pluginQuasar.configs.recommended(),
  js.configs.recommended,
  pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.ts', '**/*.vue'],
    rules: {
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
    },
  },
  vueTsConfigs.recommendedTypeChecked,
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      'prefer-promise-reject-errors': 'off',
      'vue/v-slot-style': ['warn', 'shorthand'],
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    files: ['test/**/*.ts', '*.config.ts', '*.config.js'],
    extends: [vueTsConfigs.disableTypeChecked],
  },
  prettierSkipFormatting,
);
