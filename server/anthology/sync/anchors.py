"""Position anchors: jump to any position of a keyset-paginated list without OFFSET.

``anchors[i]`` is the sort key of the row at position ``i * STEP - 1`` (the key to read
*after* to start at position ``i * STEP``); ``anchors[0]`` is ``None`` (start of list).
Anchors are built from index-only key scans on demand and cached per subscription.
"""

from collections.abc import Awaitable, Callable

from anthology.sync.streams import SortKey

STEP = 1000
SCAN_BATCH = 10 * STEP

KeyScan = Callable[[SortKey | None, int], Awaitable[list[SortKey]]]


class Anchors:
    def __init__(self, scan: KeyScan, step: int = STEP, scan_batch: int = SCAN_BATCH) -> None:
        self._scan = scan
        self._step = step
        self._scan_batch = scan_batch
        self._anchors: list[SortKey | None] = [None]
        self._complete = False  # True once the end of the list was reached while building

    async def start_key(self, position: int) -> tuple[SortKey | None, bool]:
        """Return ``(after, reachable)``: read rows after ``after`` to start at ``position``.

        ``reachable`` is False when the list certainly ends before ``position``. When it is
        True the position may still be exactly at the end; reading rows then returns none.
        """
        index = position // self._step
        await self._build_until(index)
        if index >= len(self._anchors):
            return None, False
        after = self._anchors[index]
        skip = position - index * self._step
        if skip == 0:
            return after, True
        keys = await self._scan(after, skip)
        if len(keys) < skip:
            return None, False
        return keys[-1], True

    def invalidate_from(self, key: SortKey) -> None:
        """Drop anchors at or after ``key`` (rows were inserted or removed there)."""
        for index in range(1, len(self._anchors)):
            anchor = self._anchors[index]
            if anchor is not None and anchor >= key:
                del self._anchors[index:]
                self._complete = False
                return

    def reset(self) -> None:
        self._anchors = [None]
        self._complete = False

    async def _build_until(self, index: int) -> None:
        while len(self._anchors) <= index and not self._complete:
            after = self._anchors[-1]
            keys = await self._scan(after, self._scan_batch)
            for offset in range(self._step - 1, len(keys), self._step):
                self._anchors.append(keys[offset])
            if len(keys) < self._scan_batch:
                self._complete = True
