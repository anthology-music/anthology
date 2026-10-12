/**
 * Geometry of a virtual list whose full height may exceed what browsers allow for an
 * element (Firefox ≈ 17.9 million px). Above MAX_SCROLL_HEIGHT the scroll area is
 * compressed and the scroll position is mapped linearly onto the full height.
 */
export const MAX_SCROLL_HEIGHT = 8_000_000;

export interface Geometry {
  /** Height of the scroll area (spacer). */
  scrollHeight: number;
  /** Full scrollable distance divided by the compressed one (1 = no compression). */
  ratio: number;
}

export function geometry(
  total: number,
  rowHeight: number,
  viewportHeight: number,
  maxHeight = MAX_SCROLL_HEIGHT,
): Geometry {
  const full = total * rowHeight;
  if (full <= maxHeight || full <= viewportHeight) return { scrollHeight: full, ratio: 1 };
  const ratio = (full - viewportHeight) / (maxHeight - viewportHeight);
  return { scrollHeight: maxHeight, ratio };
}

export interface Visible {
  /** Position of the first (partly) visible row. */
  first: number;
  /** Number of rows to render to fill the viewport. */
  count: number;
  /** How far the first row is scrolled out at the top, in px. */
  offset: number;
}

export function visibleRows(
  scrollTop: number,
  total: number,
  rowHeight: number,
  viewportHeight: number,
  { ratio }: Geometry,
): Visible {
  const logicalTop = scrollTop * ratio;
  const first = Math.min(Math.max(0, Math.floor(logicalTop / rowHeight)), Math.max(0, total - 1));
  const offset = logicalTop - first * rowHeight;
  const count = Math.min(Math.ceil((viewportHeight + offset) / rowHeight), total - first);
  return { first, count: Math.max(0, count), offset };
}

/** The scroll position that shows `position` at the top of the viewport. */
export function scrollTopFor(position: number, rowHeight: number, { ratio }: Geometry): number {
  return (position * rowHeight) / ratio;
}

/** The window to request: visible rows plus a buffer on both sides, capped in size. */
export function requestWindow(
  visible: Visible,
  total: number,
  buffer: number,
  maxSize = 1000,
): [number, number] {
  const start = Math.max(0, visible.first - buffer);
  const end = Math.min(total, visible.first + visible.count + buffer, start + maxSize);
  return [start, Math.max(start, end)];
}
