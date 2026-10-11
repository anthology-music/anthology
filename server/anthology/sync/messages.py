"""Protocol messages (``docs/architecture/sync-protocol.md``).

Every message is an envelope ``{type, sub?, seq?, data}``. Run
``python -m anthology.sync.messages`` to print the JSON Schema of both directions.
"""

import json
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROTOCOL_VERSION = 1
SUPPORTED_PROTOCOLS = frozenset({1})
MAX_WINDOW = 1000

SubId = Annotated[str, Field(min_length=1, max_length=64)]


class _Data(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- client → server ------------------------------------------------------


class HelloData(_Data):
    protocol: int
    token: str = Field(min_length=1)
    device_id: uuid.UUID | None = None
    last_seq: int | None = Field(default=None, ge=0)


class Hello(_Message):
    type: Literal["hello"]
    data: HelloData


class AuthData(_Data):
    token: str = Field(min_length=1)


class Auth(_Message):
    type: Literal["auth"]
    data: AuthData


class WindowData(_Data):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    def clamp(self) -> tuple[int, int]:
        end = max(self.start, min(self.end, self.start + MAX_WINDOW))
        return self.start, end


class SubscribeData(WindowData):
    stream: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    since: int | None = Field(default=None, ge=0)


class Subscribe(_Message):
    type: Literal["subscribe"]
    sub: SubId
    data: SubscribeData


class Window(_Message):
    type: Literal["window"]
    sub: SubId
    data: WindowData


class AckData(_Data):
    chunk: int = Field(ge=0)


class Ack(_Message):
    type: Literal["ack"]
    sub: SubId
    data: AckData


class Unsubscribe(_Message):
    type: Literal["unsubscribe"]
    sub: SubId
    data: _Data = Field(default_factory=_Data)


ClientMessage = Annotated[
    Hello | Auth | Subscribe | Window | Ack | Unsubscribe, Field(discriminator="type")
]
client_message = TypeAdapter(ClientMessage)


# --- server → client ------------------------------------------------------


class WelcomeData(_Data):
    protocol: int
    current_seq: int
    oldest_seq: int | None


class Welcome(_Message):
    type: Literal["welcome"] = "welcome"
    data: WelcomeData


class SnapshotMetaData(_Data):
    total: int
    counters: dict[str, int] = Field(default_factory=dict)


class SnapshotMeta(_Message):
    type: Literal["snapshot_meta"] = "snapshot_meta"
    sub: str
    seq: int
    data: SnapshotMetaData


class ChunkData(_Data):
    chunk: int
    start: int
    rows: list[dict[str, Any]]


class Chunk(_Message):
    type: Literal["chunk"] = "chunk"
    sub: str
    data: ChunkData


class DeltaData(_Data):
    op: Literal["upsert", "remove"]
    id: str
    key: list[Any] | None = None
    row: dict[str, Any] | None = None
    total: int | None = None


class Delta(_Message):
    type: Literal["delta"] = "delta"
    sub: str
    seq: int
    data: DeltaData


class Resync(_Message):
    type: Literal["resync"] = "resync"
    sub: str
    data: _Data = Field(default_factory=_Data)


class ErrorData(_Data):
    code: str
    message: str = ""


class Error(_Message):
    type: Literal["error"] = "error"
    sub: str | None = None
    data: ErrorData


ServerMessage = Annotated[
    Welcome | SnapshotMeta | Chunk | Delta | Resync | Error, Field(discriminator="type")
]
server_message = TypeAdapter(ServerMessage)


def json_schema() -> dict[str, Any]:
    return {
        "client": client_message.json_schema(),
        "server": server_message.json_schema(),
        "protocol": PROTOCOL_VERSION,
    }


if __name__ == "__main__":
    print(json.dumps(json_schema(), indent=2))
