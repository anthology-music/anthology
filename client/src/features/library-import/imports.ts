import type { LibraryImportRow, Schemas } from '@anthology/api-types';

export type ImportRow = LibraryImportRow;
export type ImportMode = Schemas['ImportMode'];
export type ImportStatus = LibraryImportRow['status'];

/** Report categories in the order the report shows them (spec: library-import, Dry-run report). */
export const CATEGORIES = [
  'new',
  'replaces_lower_quality',
  'already_present',
  'duplicate_in_source',
  'needs_review',
  'suspicious_quality',
  'broken',
  'skipped',
] as const;
export type Category = (typeof CATEGORIES)[number];

export interface Report {
  categories: Record<Category, { files: number; bytes: number }>;
  files: number;
  bytes: number;
  adds_bytes: number;
  imported: number;
  failed: { files: number; bytes: number };
}

export const statusIcons: Record<ImportStatus, string> = {
  scanning: 'manage_search',
  reported: 'fact_check',
  importing: 'sync',
  done: 'check_circle',
  cancelled: 'block',
  failed: 'error',
};

/** Modes whose originals stay referenced: only they may allow tag writes. */
export const REFERENCED_MODES: readonly ImportMode[] = ['reference', 'hardlink'];

export function report(row: ImportRow): Report | null {
  return (row.report as unknown as Report | null) ?? null;
}

export function folderName(path: string): string {
  return path.split('/').filter(Boolean).pop() ?? path;
}
