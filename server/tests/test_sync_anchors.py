import bisect

import pytest

from anthology.sync.anchors import Anchors

ROWS = [(f"k{index:06d}",) for index in range(25_000)]


class FakeKeys:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.scanned = 0

    async def __call__(self, after, limit):
        start = 0 if after is None else bisect.bisect_right(self.rows, after)
        keys = self.rows[start : start + limit]
        self.scanned += len(keys)
        return keys


async def _row_at(anchors: Anchors, keys: FakeKeys, position: int):
    after, exists = await anchors.start_key(position)
    if not exists:
        return None
    rows = await keys(after, 1)
    return rows[0] if rows else None


@pytest.mark.parametrize("position", [0, 1, 999, 1000, 1001, 12_345, 24_999])
async def test_every_position_is_reached(position: int) -> None:
    keys = FakeKeys(ROWS)
    anchors = Anchors(keys, step=1000, scan_batch=10_000)

    assert await _row_at(anchors, keys, position) == ROWS[position]


async def test_positions_after_the_end_do_not_exist() -> None:
    keys = FakeKeys(ROWS)
    anchors = Anchors(keys, step=1000, scan_batch=10_000)

    assert await _row_at(anchors, keys, 25_000) is None
    assert await anchors.start_key(40_000) == (None, False)


async def test_anchors_are_cached() -> None:
    keys = FakeKeys(ROWS)
    anchors = Anchors(keys, step=1000, scan_batch=10_000)
    await anchors.start_key(20_000)
    scanned = keys.scanned

    await anchors.start_key(19_000)

    assert keys.scanned == scanned


async def test_jump_scans_at_most_one_step_after_anchors_exist() -> None:
    keys = FakeKeys(ROWS)
    anchors = Anchors(keys, step=1000, scan_batch=10_000)
    await anchors.start_key(24_000)
    keys.scanned = 0

    await anchors.start_key(12_999)

    assert keys.scanned <= 999


async def test_invalidation_rebuilds_after_the_changed_key() -> None:
    rows = list(ROWS)
    keys = FakeKeys(rows)
    anchors = Anchors(keys, step=1000, scan_batch=10_000)
    await anchors.start_key(20_000)

    removed = rows.pop(5_000)
    anchors.invalidate_from(removed)

    assert await _row_at(anchors, keys, 20_000) == rows[20_000]
    assert await _row_at(anchors, keys, 4_999) == rows[4_999]
