<template>
  <section class="settings-section" aria-labelledby="language-title">
    <h2 id="language-title" class="settings-section__title">{{ t('language.title') }}</h2>
    <fieldset class="language__options">
      <legend class="text-muted">{{ t('language.hint') }}</legend>
      <label v-for="option in LANGUAGES" :key="option" :data-testid="`language-${option}`">
        <input
          type="radio"
          name="language"
          :value="option"
          :checked="locale === option"
          @change="choose(option)"
        />
        {{ NAMES[option] }}
      </label>
    </fieldset>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';

import { type Language, LANGUAGES, storeLanguage } from '@/i18n/language';

/** The interface language of this device (German first, English second). */
const { t, locale } = useI18n();
// Each language by its own name.
const NAMES: Record<Language, string> = { de: 'Deutsch', en: 'English' };

function choose(language: Language): void {
  storeLanguage(language);
  locale.value = language;
  document.documentElement.lang = language;
}
</script>

<style scoped>
.language__options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  border: 0;
}

.language__options label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target);
}
</style>
