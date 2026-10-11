import pytest
from pydantic import ValidationError

from anthology.sync.messages import (
    MAX_WINDOW,
    Hello,
    Subscribe,
    WindowData,
    client_message,
    json_schema,
)


def test_client_messages_are_parsed_by_type() -> None:
    hello = client_message.validate_python(
        {"type": "hello", "data": {"protocol": 1, "token": "t", "last_seq": 5}}
    )
    subscribe = client_message.validate_python(
        {"type": "subscribe", "sub": "s1", "data": {"stream": "users", "start": 0, "end": 50}}
    )

    assert isinstance(hello, Hello)
    assert hello.data.last_seq == 5
    assert isinstance(subscribe, Subscribe)
    assert subscribe.data.params == {}


@pytest.mark.parametrize(
    "message",
    [
        {"type": "nonsense"},
        {"type": "hello", "data": {"token": "t"}},
        {"type": "subscribe", "data": {"stream": "users", "start": 0, "end": 1}},
        {"type": "window", "sub": "s1", "data": {"start": -1, "end": 10}},
        {"type": "ack", "sub": "", "data": {"chunk": 0}},
    ],
)
def test_malformed_client_messages_are_rejected(message: dict) -> None:
    with pytest.raises(ValidationError):
        client_message.validate_python(message)


def test_unknown_fields_are_ignored() -> None:
    message = client_message.validate_python(
        {"type": "auth", "data": {"token": "t", "future": 1}, "extra": True}
    )

    assert message.type == "auth"


def test_window_is_clamped_to_the_maximum_size() -> None:
    assert WindowData(start=10, end=10_000).clamp() == (10, 10 + MAX_WINDOW)
    assert WindowData(start=10, end=5).clamp() == (10, 10)


def test_json_schema_covers_both_directions() -> None:
    schema = json_schema()

    client_types = {
        ref.split("/")[-1] for ref in schema["client"]["discriminator"]["mapping"].values()
    }
    server_types = set(schema["server"]["discriminator"]["mapping"])

    assert client_types == {"Hello", "Auth", "Subscribe", "Window", "Ack", "Unsubscribe"}
    assert server_types == {"welcome", "snapshot_meta", "chunk", "delta", "resync", "error"}
