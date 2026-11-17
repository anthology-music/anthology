import type { Schemas } from '@anthology/api-types';

import { getServices } from '@/services';

export type WorkType = Schemas['WorkIn']['type'];
export type CreditRole = Schemas['CreditIn']['role'];
export type RelationType = Schemas['RelationIn']['type'];
export type CreditIn = Schemas['CreditIn'];
export type WorkProblem =
  | 'cycle'
  | 'title_required'
  | 'different_musicbrainz_artists'
  | 'same_person'
  | 'relations_changed'
  | 'unknown_work'
  | 'unknown_person'
  | 'failed';

export const WORK_TYPES: WorkType[] = ['original', 'arrangement', 'medley', 'adaptation'];
export const CREDIT_ROLES: CreditRole[] = ['composer', 'lyricist', 'arranger'];

function problem(error: unknown): WorkProblem {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  const known: WorkProblem[] = [
    'cycle',
    'title_required',
    'different_musicbrainz_artists',
    'same_person',
    'relations_changed',
    'unknown_work',
    'unknown_person',
  ];
  return known.includes(detail as WorkProblem) ? (detail as WorkProblem) : 'failed';
}

const api = () => getServices().api;

export interface Created {
  id: string | null;
  problem: WorkProblem | null;
}

export async function createWork(body: Schemas['WorkIn']): Promise<Created> {
  const { data, error, response } = await api().POST('/api/v1/works', { body });
  return response.ok
    ? { id: data?.id ?? null, problem: null }
    : { id: null, problem: problem(error) };
}

export async function updateWork(
  workId: string,
  changes: Schemas['WorkPatch'],
): Promise<WorkProblem | null> {
  const { error, response } = await api().PATCH('/api/v1/works/{work_id}', {
    params: { path: { work_id: workId } },
    body: changes,
  });
  return response.ok ? null : problem(error);
}

export async function deleteWork(workId: string): Promise<WorkProblem | null> {
  const { error, response } = await api().DELETE('/api/v1/works/{work_id}', {
    params: { path: { work_id: workId } },
  });
  return response.ok ? null : problem(error);
}

export async function setCredits(workId: string, credits: CreditIn[]): Promise<WorkProblem | null> {
  const { error, response } = await api().PUT('/api/v1/works/{work_id}/credits', {
    params: { path: { work_id: workId } },
    body: { credits },
  });
  return response.ok ? null : problem(error);
}

export async function addRelation(
  workId: string,
  targetId: string,
  type: RelationType,
): Promise<WorkProblem | null> {
  const { error, response } = await api().POST('/api/v1/works/{work_id}/relations', {
    params: { path: { work_id: workId } },
    body: { target_id: targetId, type },
  });
  return response.ok ? null : problem(error);
}

export async function removeRelation(relationId: string): Promise<WorkProblem | null> {
  const { error, response } = await api().DELETE('/api/v1/works/relations/{relation_id}', {
    params: { path: { relation_id: relationId } },
  });
  return response.ok ? null : problem(error);
}

export async function orderRelations(
  workId: string,
  relationIds: string[],
): Promise<WorkProblem | null> {
  const { error, response } = await api().PUT('/api/v1/works/{work_id}/relations/order', {
    params: { path: { work_id: workId } },
    body: { relation_ids: relationIds },
  });
  return response.ok ? null : problem(error);
}

export async function linkRecording(
  workId: string,
  recordingId: string,
): Promise<WorkProblem | null> {
  const { error, response } = await api().PUT('/api/v1/works/{work_id}/recordings/{recording_id}', {
    params: { path: { work_id: workId, recording_id: recordingId } },
  });
  return response.ok ? null : problem(error);
}

export async function unlinkRecording(
  workId: string,
  recordingId: string,
): Promise<WorkProblem | null> {
  const { error, response } = await api().DELETE(
    '/api/v1/works/{work_id}/recordings/{recording_id}',
    { params: { path: { work_id: workId, recording_id: recordingId } } },
  );
  return response.ok ? null : problem(error);
}

export async function renamePerson(personId: string, name: string): Promise<WorkProblem | null> {
  const { error, response } = await api().PATCH('/api/v1/persons/{person_id}', {
    params: { path: { person_id: personId } },
    body: { name },
  });
  return response.ok ? null : problem(error);
}

export async function mergePerson(personId: string, targetId: string): Promise<WorkProblem | null> {
  const { error, response } = await api().POST('/api/v1/persons/{person_id}/merge', {
    params: { path: { person_id: personId } },
    body: { target_id: targetId },
  });
  return response.ok ? null : problem(error);
}
