import type { User } from '@/features/users/session';

export type JobStatus = 'queued' | 'running' | 'paused' | 'done' | 'failed' | 'cancelled';

export interface JobRow {
  id: string;
  type: string;
  title: string;
  status: JobStatus;
  created_by: string;
  created_by_name: string;
  total_items: number;
  done_items: number;
  failed_items: number;
  progress: number;
  error: string | null;
}

export interface JobItemRow {
  position: number;
  title: string;
  status: JobStatus;
  progress: number;
  outcome: string | null;
  message: string | null;
}

export type JobAction = 'pause' | 'resume' | 'cancel';

/** Status shown with an icon and a text, never colour alone (client/AGENTS.md). */
export const statusIcons: Record<JobStatus, string> = {
  queued: 'schedule',
  running: 'sync',
  paused: 'pause_circle',
  done: 'check_circle',
  failed: 'error',
  cancelled: 'cancel',
};

/** Only the creator and admins may pause, resume or cancel a job (spec: jobs). */
export function canControl(job: JobRow, user: User | null): boolean {
  return user !== null && (user.role === 'admin' || job.created_by === user.id);
}

export function percent(progress: number): number {
  return Math.round(Math.min(Math.max(progress, 0), 1) * 100);
}

/** Control actions valid in a status (server answers 409 for others). */
export function actionsFor(status: JobStatus): JobAction[] {
  if (status === 'queued' || status === 'running') return ['pause', 'cancel'];
  if (status === 'paused') return ['resume', 'cancel'];
  return [];
}
