"""Crash safety: a write killed half-way leaves the old or the new state, never a partial one."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tagger.config import Settings
from tagger.service import Tagger
from tests.conftest import Volumes

# Runs a write in a child process; the update corrupts the file being written, signals the
# parent and hangs, so the parent can kill the process in the middle of the write.
CHILD = """
import json, sys, time
from pathlib import Path
from tagger import service
from tagger.config import Settings
from tagger.models import WriteRequest

args = json.loads(sys.argv[1])

def hanging_updater(tags, replace_all, images):
    def update(path):
        with open(path, "r+b") as handle:
            handle.seek(0)
            handle.write(b"\\xff" * 4096)
        Path(args["ready"]).touch()
        time.sleep(60)
    return update

service._updater = hanging_updater
tagger = service.Tagger(Settings(**args["settings"]))
files = [{"path": args["path"], "tags": {"title": "X"}}]
tagger.write(WriteRequest(mode=args["mode"], files=files))
"""


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def kill_during_write(volumes: Volumes, path: Path, mode: str) -> None:
    ready = volumes.cache / "ready"
    arguments = {
        "mode": mode,
        "path": str(path),
        "ready": str(ready),
        "settings": volumes.settings.model_dump(),
    }
    child = subprocess.Popen([sys.executable, "-c", CHILD, json.dumps(arguments)])
    try:
        for _ in range(200):
            if ready.exists() or child.poll() is not None:
                break
            time.sleep(0.05)
        assert ready.exists(), "the child did not reach the write"
    finally:
        os.kill(child.pid, signal.SIGKILL)
        child.wait()


def restart(settings: Settings) -> list[str]:
    return Tagger(settings).recover()


def test_killed_atomic_write_leaves_the_original_unchanged(
    volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["flac"])
    before = checksum(path)

    kill_during_write(volumes, path, "atomic")
    leftovers = [p for p in path.parent.iterdir() if p != path]
    recovered = restart(volumes.settings)

    assert checksum(path) == before
    assert len(leftovers) == 1  # the temp file of the interrupted write …
    assert recovered == [str(leftovers[0])]
    assert [p.name for p in path.parent.iterdir()] == [path.name]  # … is removed on start


def test_killed_in_place_write_is_restored_on_start(
    volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["mp3"], volume="imports")
    link = volumes.library / "linked.mp3"
    link.hardlink_to(path)
    before = checksum(path)

    kill_during_write(volumes, path, "in_place")
    assert checksum(path) != before  # the file was left half-written
    recovered = restart(volumes.settings)

    assert recovered == [str(path)]
    assert checksum(path) == before
    assert path.stat().st_nlink == 2
    assert link.stat().st_ino == path.stat().st_ino
    assert list((volumes.cache / "tagger" / "journal").iterdir()) == []
