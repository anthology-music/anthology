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
    # Fields with defaults (e.g. ``type``) are always sent, so they are required in the
    # serialization schema used for the generated client types.
    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)


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


class SetWindow(_Message):
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
    Hello | Auth | Subscribe | SetWindow | Ack | Unsubscribe, Field(discriminator="type")
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
    counters: dict[str, int] | None = None


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


class ErrorMessage(_Message):
    type: Literal["error"] = "error"
    sub: str | None = None
    data: ErrorData


ServerMessage = Annotated[
    Welcome | SnapshotMeta | Chunk | Delta | Resync | ErrorMessage, Field(discriminator="type")
]
server_message = TypeAdapter(ServerMessage)


def json_schema() -> dict[str, Any]:
    """One schema for both directions: ``ClientMessage`` and ``ServerMessage`` in ``$defs``.

    Server messages use the serialization schema, so fields the server always sends
    (such as ``type``) are required.
    """
    client = client_message.json_schema()
    server = server_message.json_schema(mode="serialization")
    definitions = {**client.pop("$defs"), **server.pop("$defs")}
    definitions["ClientMessage"] = {**client, "title": "ClientMessage"}
    definitions["ServerMessage"] = {**server, "title": "ServerMessage"}
    return {
        "title": "SyncProtocol",
        "protocol": PROTOCOL_VERSION,
        "type": "object",
        "properties": {
            "client": {"$ref": "#/$defs/ClientMessage"},
            "server": {"$ref": "#/$defs/ServerMessage"},
        },
        "$defs": definitions,
    }


if __name__ == "__main__":
    print(json.dumps(json_schema(), indent=2))
