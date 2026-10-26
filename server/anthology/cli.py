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

    library = dev_commands.add_parser(
        "seed-library",
        help="fill the library with a generated test library (requires ANTHOLOGY_DEV_DEMO=true)",
    )
    library.add_argument("--tracks", type=int, default=500_000)
    library.add_argument("--reset", action="store_true", help="replace an existing library")

    conflicts = dev_commands.add_parser(
        "seed-conflicts",
        help="create tag conflicts for the first albums (requires ANTHOLOGY_DEV_DEMO=true)",
    )
    conflicts.add_argument("--releases", type=int, default=3)

    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command == "dev" and args.dev_command == "seed-demo":
        return seed_demo(settings, args.rows, args.reset)
    if args.command == "dev" and args.dev_command == "seed-library":
        return seed_library(settings, args.tracks, args.reset)
    if args.command == "dev" and args.dev_command == "seed-conflicts":
        return seed_conflicts(settings, args.releases)
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


def seed_library(settings: Settings, tracks: int, reset: bool) -> int:
    if not settings.dev_demo:
        print(
            "refusing to seed: set ANTHOLOGY_DEV_DEMO=true (developer installations only)",
            file=sys.stderr,
        )
        return 1
    try:
        from anthology.library.seed import LibraryNotEmptyError, seed_library
    except ImportError:  # pragma: no cover - production images have no generator
        print("the library generator is missing: run uv sync (dev dependencies)", file=sys.stderr)
        return 1

    async def run() -> dict[str, int]:
        engine = create_engine(settings)
        try:
            return await seed_library(engine, tracks, reset)
        finally:
            await engine.dispose()

    try:
        counters = asyncio.run(run())
    except LibraryNotEmptyError as error:
        print(f"refusing to seed: {error}", file=sys.stderr)
        return 1
    summary = ", ".join(f"{value} {name}" for name, value in counters.items())
    print(f"library ready: {summary}; reconnect clients to see it")
    return 0


def seed_conflicts(settings: Settings, releases: int) -> int:
    if not settings.dev_demo:
        print(
            "refusing to seed: set ANTHOLOGY_DEV_DEMO=true (developer installations only)",
            file=sys.stderr,
        )
        return 1
    from anthology.tagging.seed import seed_conflicts as seed

    async def run() -> int:
        engine = create_engine(settings)
        try:
            return await seed(engine, releases)
        finally:
            await engine.dispose()

    print(f"tag conflicts ready: {asyncio.run(run())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
