/** Durations of works as "m:ss" (or "h:mm:ss"). */
export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

/** Seconds of "m:ss", "h:mm:ss" or plain minutes; null for empty, undefined if invalid. */
export function parseDuration(text: string): number | null | undefined {
  const value = text.trim();
  if (!value) return null;
  if (!/^\d+(:\d{1,2}){0,2}$/.test(value)) return undefined;
  const parts = value.split(':').map(Number);
  if (parts.length === 1) return parts[0]! * 60;
  if (parts.slice(1).some((part) => part > 59)) return undefined;
  return parts.reduce((total, part) => total * 60 + part, 0);
}
