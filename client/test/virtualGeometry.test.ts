import { describe, expect, it } from 'vitest';

import {
  MAX_SCROLL_HEIGHT,
  geometry,
  requestWindow,
  scrollTopFor,
  visibleRows,
} from '@/components/virtualGeometry';

const ROW = 52;
const VIEW = 600;

describe('virtual list geometry', () => {
  it('uses the full height for small lists', () => {
    expect(geometry(1000, ROW, VIEW)).toEqual({ scrollHeight: 52_000, ratio: 1 });
  });

  it('compresses lists taller than the browser limit', () => {
    const geo = geometry(500_000, ROW, VIEW);

    expect(geo.scrollHeight).toBe(MAX_SCROLL_HEIGHT);
    expect(geo.ratio).toBeGreaterThan(3);
  });

  it.each([0, 1, 12_345, 250_000, 499_000])(
    'maps the scroll position of row %i back to that row',
    (position) => {
      const geo = geometry(500_000, ROW, VIEW);

      const visible = visibleRows(scrollTopFor(position, ROW, geo), 500_000, ROW, VIEW, geo);

      expect(visible.first).toBe(position);
      expect(visible.offset).toBeCloseTo(0, 6);
    },
  );

  it('shows the last rows when scrolled to the end', () => {
    const geo = geometry(500_000, ROW, VIEW);
    const maxScroll = geo.scrollHeight - VIEW;

    const visible = visibleRows(maxScroll, 500_000, ROW, VIEW, geo);

    expect(visible.first + visible.count).toBe(500_000);
  });

  it('renders enough rows to fill the viewport including a partly visible one', () => {
    const geo = geometry(1000, ROW, VIEW);

    const visible = visibleRows(26, 1000, ROW, VIEW, geo);

    expect(visible).toEqual({ first: 0, count: 13, offset: 26 });
  });

  it('requests the visible rows plus buffer, clamped to the list', () => {
    expect(requestWindow({ first: 0, count: 12, offset: 0 }, 1000, 50)).toEqual([0, 62]);
    expect(requestWindow({ first: 500, count: 12, offset: 0 }, 1000, 50)).toEqual([450, 562]);
    expect(requestWindow({ first: 990, count: 10, offset: 0 }, 1000, 50)).toEqual([940, 1000]);
    expect(requestWindow({ first: 0, count: 2000, offset: 0 }, 5000, 50, 1000)).toEqual([0, 1000]);
  });
});
