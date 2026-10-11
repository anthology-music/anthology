"""Command line: ``anthology <command>``."""

import argparse
import asyncio
import sys

from anthology.core.config import Settings, get_settings
from anthology.db import create_engine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="anthology")
    commands = parser.add_subparsers(dest="command", required=True)

    dev = commands.add_parser("dev", help="developer tools")
    dev_commands = dev.add_subparsers(dest="dev_command", required=True)
    seed = dev_commands.add_parser(
        "seed-demo", help="create and fill the demo table (requires ANTHOLOGY_DEV_DEMO=true)"
    )
    seed.add_argument("--rows", type=int, default=500_000)
    seed.add_argument("--reset", action="store_true", help="drop and recreate the table")

    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "dev" and args.dev_command == "seed-demo":
        return seed_demo(settings, args.rows, args.reset)
    return 2  # pragma: no cover - argparse rejects unknown commands


def seed_demo(settings: Settings, rows: int, reset: bool) -> int:
    if not settings.dev_demo:
        print(
            "refusing to seed: set ANTHOLOGY_DEV_DEMO=true (developer installations only)",
            file=sys.stderr,
        )
        return 1
    from anthology.sync.demo import seed

    async def run() -> int:
        engine = create_engine(settings)
        try:
            return await seed(engine, rows, reset)
        finally:
            await engine.dispose()

    inserted = asyncio.run(run())
    print(f"demo table ready: {rows} rows ({inserted} inserted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
