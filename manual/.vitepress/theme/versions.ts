import { ref, type Ref } from 'vue';

// The published versions are listed in versions.json at the site root (written by
// scripts/publish-site.mjs) and read at runtime, so a manual built earlier also offers the
// releases published after it.

export interface Release {
  /** Directory below the site root, e.g. "v0.1" */
  path: string;
  /** Tag of the release published there, e.g. "v0.1.0" */
  tag: string;
}

export interface Versions {
  latest: string | null;
  releases: Release[];
  next: boolean;
}

let loaded: Ref<Versions | null> | undefined;

export function useVersions(siteRoot: string): Ref<Versions | null> {
  if (!loaded) {
    loaded = ref(null);
    if (typeof window !== 'undefined') {
      fetch(`${siteRoot}versions.json`, { cache: 'no-cache' })
        .then((response) => (response.ok ? response.json() : null))
        .then((versions: Versions | null) => {
          loaded!.value = versions;
        })
        .catch(() => undefined);
    }
  }
  return loaded;
}
