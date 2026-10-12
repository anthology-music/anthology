"""Contract tests: the core's tagger client against a real tagger (HTTP only).

Run when ANTHOLOGY_TEST_TAGGER_URL and ANTHOLOGY_TEST_TAGGER_ROOT are set; the tagger must
accept paths below that root and use ``<root>/cache`` as its cache root. CI starts the tagger
from services/tagger. Test media is generated with FFmpeg.
"""

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from anthology.core.services import ServiceState
from anthology.tagging.schemas import CopyFile, TagFields, WriteFile
from anthology.tagging.tagger_client import TaggerClient, check_tagger

TAGGER_URL = os.environ.get("ANTHOLOGY_TEST_TAGGER_URL", "")
TAGGER_ROOT = os.environ.get("ANTHOLOGY_TEST_TAGGER_ROOT", "")

pytestmark = [
    pytest.mark.tagger_contract,
    pytest.mark.skipif(
        not (TAGGER_URL and TAGGER_ROOT), reason="ANTHOLOGY_TEST_TAGGER_URL/_ROOT not set"
    ),
]


@pytest.fixture
def workdir() -> Path:
    directory = Path(TAGGER_ROOT) / "library" / f"contract-{uuid.uuid4().hex}"
    directory.mkdir(parents=True)
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def flac(workdir: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.fail("ffmpeg is required for the contract tests")
    target = workdir / "tone.flac"
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
            "-i", "sine=frequency=440:duration=0.3", "-c:a", "flac", str(target),
        ],
        check=True,
    )  # fmt: skip
    return target


@pytest.fixture
async def tagger() -> TaggerClient:
    client = TaggerClient(TAGGER_URL, batch_size=200)
    yield client
    await client.aclose()


async def test_health_is_compatible(tagger: TaggerClient) -> None:
    seen = await check_tagger(tagger)

    assert seen.status == ServiceState.AVAILABLE
    assert seen.interface is not None and seen.interface.startswith("1.")


async def test_write_read_and_copy(tagger: TaggerClient, flac: Path, workdir: Path) -> None:
    tags = TagFields(title="Contract", track_number=2, track_total=9, genres=["Blasmusik"])
    target = Path(TAGGER_ROOT) / "cache" / workdir.name / "copy.flac"

    [written] = await tagger.write("atomic", [WriteFile(path=str(flac), tags=tags)])
    [read] = await tagger.read([str(flac)])
    [copied] = await tagger.copy(
        [CopyFile(source=str(flac), target=str(target), tags=TagFields(title="Copy"))]
    )
    [copy] = await tagger.read([str(target)])
    shutil.rmtree(target.parent, ignore_errors=True)

    assert written.ok, written
    assert read.audio is not None and read.audio.format == "flac" and read.audio.lossless
    assert read.tags == tags
    assert copied.ok, copied
    assert copy.tags == TagFields(title="Copy")


async def test_large_batches_are_split(tagger: TaggerClient, flac: Path, workdir: Path) -> None:
    paths = [str(flac)] + [str(workdir / f"missing-{index}.flac") for index in range(249)]

    results = await tagger.read(paths)

    assert len(results) == 250
    assert results[0].ok
    assert {result.error for result in results[1:]} == {"not_found"}
