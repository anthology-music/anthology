"""Position anchors: jump to any position of a keyset-paginated list without OFFSET.

``anchors[i]`` is the sort key of the row at position ``i * STEP - 1`` (the key to read
*after* to start at position ``i * STEP``); ``anchors[0]`` is ``None`` (start of list).
Anchors are computed in the database (only every ``STEP``-th key is returned) on demand
and cached per subscription.
"""

from collections.abc import Awaitable, Callable

from anthology.sync.streams import SortKey

STEP = 1000
ANCHOR_BATCH = 20  # extra anchors computed beyond the requested position

KeyScan = Callable[[SortKey | None, int], Awaitable[list[SortKey]]]
AnchorScan = Callable[[SortKey | None, int, int], Awaitable[list[SortKey]]]


class Anchors:
    def __init__(
        self,
        scan: KeyScan,
        anchor_scan: AnchorScan,
        step: int = STEP,
        anchor_batch: int = ANCHOR_BATCH,
    ) -> None:
        self._scan = scan
        self._anchor_scan = anchor_scan
        self._step = step
        self._anchor_batch = anchor_batch
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
            count = index + 1 - len(self._anchors) + self._anchor_batch
            keys = await self._anchor_scan(self._anchors[-1], self._step, count)
            self._anchors.extend(keys)
            if len(keys) < count:
                self._complete = True
