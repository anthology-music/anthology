import type {
  Confidence,
  ReviewItemRow,
  ReviewOrigin,
  ReviewStatus,
  ReviewType,
  Schemas,
} from '@anthology/api-types';

import { getServices } from '@/services';
import type { Row } from '@/sync/subscription';

export const STATUSES: readonly ReviewStatus[] = [
  'open',
  'deferred',
  'accepted',
  'rejected',
  'obsolete',
];
export const TYPES: readonly ReviewType[] = [
  'recording_match',
  'musicbrainz_suggestion',
  'import_title',
  'import_replacement',
  'quality_finding',
];
export const ORIGINS: readonly ReviewOrigin[] = [
  'fuzzy_match',
  'musicbrainz',
  'import',
  'quality_analysis',
];
export const CONFIDENCES: readonly Confidence[] = ['high', 'medium', 'low'];

/** The list's selection: the subscription parameters and the rule of bulk decisions. */
export interface ReviewFilter {
  status: ReviewStatus;
  type: ReviewType | null;
  origin: ReviewOrigin | null;
  confidence: Confidence | null;
}

export const DEFAULT_FILTER: ReviewFilter = {
  status: 'open',
  type: null,
  origin: null,
  confidence: null,
};

/** Subscription parameters (unset filters are left out). */
export function filterParams(filter: ReviewFilter): Record<string, string> {
  const params: Record<string, string> = { status: filter.status };
  if (filter.type) params.type = filter.type;
  if (filter.origin) params.origin = filter.origin;
  if (filter.confidence) params.confidence = filter.confidence;
  return params;
}

export const entry = (row: Row) => row as unknown as ReviewItemRow;

export type Decision = Schemas['ReviewDecisionIn']['decision'];

export type DecisionResult =
  | { kind: 'decided'; status: ReviewStatus }
  | { kind: 'job'; selected: number }
  | { kind: 'nothing' }
  | { kind: 'error'; code: string };

/** Decide entries by ID (multi-select) or by rule; file work and bulk decisions run as a job. */
export async function decide(
  selection: { ids: string[] } | { rule: ReviewFilter },
  decision: Decision,
  choice: string | null = null,
): Promise<DecisionResult> {
  const { data, error, response } = await getServices().api.POST('/api/v1/review/decisions', {
    body: { ...selection, decision, choice },
  });
  if (!data) {
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    return { kind: 'error', code: typeof detail === 'string' ? detail : String(response.status) };
  }
  if (data.status) return { kind: 'decided', status: data.status };
  if (data.job_id) return { kind: 'job', selected: data.selected };
  return { kind: 'nothing' };
}
