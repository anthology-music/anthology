"""Developer demo job (``ANTHOLOGY_DEV_DEMO=true``): items that wait and report progress."""

import asyncio
from dataclasses import dataclass

from anthology.jobs.handlers import ItemContext, ItemResult

DEMO_TYPE = "demo"


@dataclass
class DemoJobHandler:
    type: str = DEMO_TYPE
    parallel_items: int = 4

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        seconds = float(ctx.params.get("seconds_per_item", 1.0))
        steps = max(1, int(seconds / 0.25))
        for step in range(steps):
            if await ctx.cancelled():
                return ItemResult(message="stopped")
            await asyncio.sleep(seconds / steps)
            await ctx.report((step + 1) / steps, f"{step + 1}/{steps}")
        return ItemResult(message="done")
