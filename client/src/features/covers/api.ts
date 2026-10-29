import type { Schemas } from '@anthology/api-types';

import { getServices } from '@/services';

export type GalleryImage = Schemas['GalleryImage'];
export type ImageKind = GalleryImage['kind'];
export type CoverProblem = 'invalid_image' | 'image_too_large' | 'unsupported_image' | 'failed';

function problem(error: unknown): CoverProblem {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return detail === 'invalid_image' ||
    detail === 'image_too_large' ||
    detail === 'unsupported_image'
    ? detail
    : 'failed';
}

/** The file is the request body (JPEG, PNG, WebP; spec: covers, editors and admins only). */
function raw(file: File) {
  return {
    body: file as never,
    bodySerializer: (body: unknown) => body as BodyInit,
    headers: { 'Content-Type': file.type },
  };
}

export async function uploadReleaseCover(
  releaseId: string,
  file: File,
): Promise<CoverProblem | null> {
  const { error, response } = await getServices().api.PUT('/api/v1/releases/{release_id}/cover', {
    params: { path: { release_id: releaseId } },
    ...raw(file),
  });
  return response.ok ? null : problem(error);
}

export async function removeReleaseCover(releaseId: string): Promise<boolean> {
  const { response } = await getServices().api.DELETE('/api/v1/releases/{release_id}/cover', {
    params: { path: { release_id: releaseId } },
  });
  return response.ok;
}

export async function gallery(releaseId: string): Promise<GalleryImage[]> {
  const { data } = await getServices().api.GET('/api/v1/releases/{release_id}/images', {
    params: { path: { release_id: releaseId } },
  });
  return data ?? [];
}

export async function addGalleryImage(
  releaseId: string,
  kind: ImageKind,
  file: File,
): Promise<GalleryImage[] | CoverProblem> {
  const { data, error, response } = await getServices().api.POST(
    '/api/v1/releases/{release_id}/images',
    { params: { path: { release_id: releaseId }, query: { kind } }, ...raw(file) },
  );
  return response.ok && data ? data : problem(error);
}

export async function removeGalleryImage(releaseId: string, entryId: string): Promise<boolean> {
  const { response } = await getServices().api.DELETE(
    '/api/v1/releases/{release_id}/images/{entry_id}',
    { params: { path: { release_id: releaseId, entry_id: entryId } } },
  );
  return response.ok;
}

export async function orderGallery(
  releaseId: string,
  ids: string[],
): Promise<GalleryImage[] | null> {
  const { data } = await getServices().api.PUT('/api/v1/releases/{release_id}/images/order', {
    params: { path: { release_id: releaseId } },
    body: { ids },
  });
  return data ?? null;
}
