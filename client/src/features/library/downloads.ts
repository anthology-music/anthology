import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getServices } from '@/services';

export type DownloadNotice = 'untagged' | 'failed';

/** Saves a link the way the browser saves an attachment (spec: library, Context-tagged downloads). */
export type SaveLink = (url: string, fileName: string) => void;

let saveLink: SaveLink = (url, fileName) => {
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.rel = 'noopener';
  document.body.append(link);
  link.click();
  link.remove();
};

/** Tests: replace the browser download. */
export function setSaveLink(save: SaveLink): void {
  saveLink = save;
}

/**
 * Downloads of a track (its original with the tags of the context it is shown in) or of a
 * whole album as zip. The server answers with a signed URL; without the tagger the files carry
 * no context tags, which the notice says.
 */
export const useDownloadStore = defineStore('libraryDownloads', () => {
  const notice = ref<DownloadNotice | null>(null);
  const busy = ref(false);

  async function start(kind: 'tracks' | 'releases', id: string): Promise<void> {
    busy.value = true;
    notice.value = null;
    try {
      const api = getServices().api;
      const { data } =
        kind === 'tracks'
          ? await api.POST('/api/v1/library/tracks/{track_id}/download', {
              params: { path: { track_id: id } },
            })
          : await api.POST('/api/v1/library/releases/{release_id}/download', {
              params: { path: { release_id: id } },
            });
      if (!data) {
        notice.value = 'failed';
        return;
      }
      saveLink(data.url, data.file_name);
      if (!data.tagged) notice.value = 'untagged';
    } catch {
      notice.value = 'failed';
    } finally {
      busy.value = false;
    }
  }

  return {
    notice,
    busy,
    downloadTrack: (id: string) => start('tracks', id),
    downloadRelease: (id: string) => start('releases', id),
    dismiss: () => {
      notice.value = null;
    },
  };
});
