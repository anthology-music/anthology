<template>
  <q-card class="gallery" data-testid="gallery">
    <q-card-section class="gallery__head">
      <h2 class="gallery__title">{{ t('covers.gallery.title', { title }) }}</h2>
      <q-btn v-close-popup flat round icon="close" :aria-label="t('covers.gallery.close')" />
    </q-card-section>
    <q-card-section>
      <p v-if="loading" class="text-muted" role="status">{{ t('covers.gallery.loading') }}</p>
      <p v-else-if="images.length === 0" class="text-muted" data-testid="gallery-empty">
        {{ t('covers.gallery.empty') }}
      </p>
      <ol v-else class="gallery__list">
        <li
          v-for="(image, index) in images"
          :key="image.id"
          class="gallery__item"
          :data-testid="`gallery-image-${index}`"
        >
          <a
            v-if="image.image_id && grant.url(image.image_id, 'full')"
            :href="grant.url(image.image_id, 'full')!"
            target="_blank"
            rel="noopener"
            class="gallery__link"
          >
            <CoverImage
              :image-id="image.image_id"
              :title="t(`covers.kinds.${image.kind}`)"
              :px="180"
            />
          </a>
          <CoverImage v-else :image-id="null" :title="t(`covers.kinds.${image.kind}`)" :px="180" />
          <span class="gallery__kind">{{ t(`covers.kinds.${image.kind}`) }}</span>
          <span v-if="canEdit" class="gallery__actions">
            <q-btn
              flat
              dense
              round
              icon="arrow_upward"
              :disable="index === 0 || busy"
              :aria-label="t('covers.gallery.earlier')"
              @click="move(index, -1)"
            />
            <q-btn
              flat
              dense
              round
              icon="arrow_downward"
              :disable="index === images.length - 1 || busy"
              :aria-label="t('covers.gallery.later')"
              @click="move(index, 1)"
            />
            <q-btn
              flat
              dense
              round
              icon="delete"
              :disable="busy"
              :aria-label="t('covers.gallery.remove')"
              :data-testid="`gallery-remove-${index}`"
              @click="remove(image.id)"
            />
          </span>
        </li>
      </ol>
    </q-card-section>
    <q-card-section v-if="canEdit" class="gallery__add">
      <label class="gallery__field">
        <span>{{ t('covers.gallery.kind') }}</span>
        <select v-model="kind" data-testid="gallery-kind">
          <option v-for="option in KINDS" :key="option" :value="option">
            {{ t(`covers.kinds.${option}`) }}
          </option>
        </select>
      </label>
      <label class="gallery__field">
        <span>{{ t('covers.gallery.add') }}</span>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          :disabled="busy"
          data-testid="gallery-file"
          @change="add"
        />
      </label>
    </q-card-section>
    <p v-if="problem" class="gallery__problem" role="alert" data-testid="gallery-problem">
      <q-icon name="error" aria-hidden="true" /> {{ t(`covers.problem.${problem}`) }}
    </p>
  </q-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

import {
  addGalleryImage,
  type CoverProblem,
  gallery,
  type GalleryImage,
  type ImageKind,
  orderGallery,
  removeGalleryImage,
} from '../api';
import { useImageGrant } from '../grant';
import CoverImage from './CoverImage.vue';

/** The images of an album beyond its cover, loaded when opened (spec: covers, Image
 * gallery); editors add, remove and reorder them. */
const props = defineProps<{ releaseId: string; title: string; canEdit: boolean }>();

const KINDS: ImageKind[] = ['back', 'booklet', 'disc', 'other'];
const { t } = useI18n();
const grant = useImageGrant();
const images = ref<GalleryImage[]>([]);
const loading = ref(true);
const busy = ref(false);
const kind = ref<ImageKind>('booklet');
const problem = ref<CoverProblem | null>(null);

onMounted(async () => {
  images.value = await gallery(props.releaseId);
  loading.value = false;
});

async function add(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  busy.value = true;
  const result = await addGalleryImage(props.releaseId, kind.value, file);
  busy.value = false;
  input.value = '';
  if (typeof result === 'string') problem.value = result;
  else {
    problem.value = null;
    images.value = result;
  }
}

async function remove(entryId: string): Promise<void> {
  busy.value = true;
  if (await removeGalleryImage(props.releaseId, entryId))
    images.value = images.value.filter((image) => image.id !== entryId);
  else problem.value = 'failed';
  busy.value = false;
}

async function move(index: number, by: -1 | 1): Promise<void> {
  const ids = images.value.map((image) => image.id);
  [ids[index], ids[index + by]] = [ids[index + by]!, ids[index]!];
  busy.value = true;
  const ordered = await orderGallery(props.releaseId, ids);
  busy.value = false;
  if (ordered) images.value = ordered;
  else problem.value = 'failed';
}
</script>

<style scoped>
.gallery {
  width: min(760px, 100vw);
}

.gallery__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gallery__title {
  margin: 0;
  font-size: var(--text-lg);
}

.gallery__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.gallery__item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.gallery__link {
  display: inline-flex;
}

.gallery__kind {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.gallery__actions {
  display: flex;
  gap: var(--space-1);
}

.gallery__add {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  border-top: 1px solid var(--color-border);
}

.gallery__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-sm);
}

.gallery__field select {
  min-height: 44px;
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.gallery__problem {
  margin: 0 var(--space-4) var(--space-4);
  color: var(--color-status-error);
}
</style>
