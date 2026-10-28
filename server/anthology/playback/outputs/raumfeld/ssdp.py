"""SSDP discovery of Raumfeld hosts (UPnP Device Architecture 1.0, section 1.3.2): an M-SEARCH
for the host's configuration device; every answer names the host in its ``LOCATION``. Without
multicast (a container without host networking) no answer arrives, which is harmless."""

import asyncio
import contextlib
import logging
import socket
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

GROUP = ("239.255.255.250", 1900)
CONFIG_DEVICE = "urn:schemas-raumfeld-com:device:ConfigDevice:1"
# The host's configuration service listens here (docs/architecture/raumfeld.md).
CONFIG_PORT = 47365
WAIT_SECONDS = 3


def m_search(target: str = CONFIG_DEVICE, wait: int = WAIT_SECONDS) -> bytes:
    return (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {GROUP[0]}:{GROUP[1]}\r\n"
        'MAN: "ssdp:discover"\r\n'
        f"MX: {wait}\r\n"
        f"ST: {target}\r\n"
        "\r\n"
    ).encode()


def headers(datagram: bytes) -> dict[str, str]:
    lines = datagram.decode("utf-8", "replace").split("\r\n")
    found = {}
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if separator:
            found[name.strip().lower()] = value.strip()
    return found


def host_address(datagram: bytes) -> str | None:
    """The configuration service's address (host:port) from an answer for the config device."""
    found = headers(datagram)
    if CONFIG_DEVICE not in (found.get("st", ""), found.get("nt", "")):
        return None
    location = urlsplit(found.get("location", ""))
    if not location.hostname:
        return None
    return f"{location.hostname}:{CONFIG_PORT}"


class _Answers(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.found: dict[str, None] = {}

    def datagram_received(self, data: bytes, addr) -> None:
        address = host_address(data)
        if address is not None:
            self.found[address] = None


async def search(wait: float = WAIT_SECONDS) -> list[str]:
    """Addresses of the Raumfeld hosts that answered within ``wait`` seconds."""
    loop = asyncio.get_running_loop()
    try:
        transport, answers = await loop.create_datagram_endpoint(
            _Answers,
            local_addr=("0.0.0.0", 0),  # noqa: S104 (answers come to the sending socket)
            family=socket.AF_INET,
        )
    except OSError:
        logger.debug("SSDP is not available", exc_info=True)
        return []
    try:
        with contextlib.suppress(OSError):
            transport.sendto(m_search(), GROUP)
        await asyncio.sleep(wait)
    finally:
        transport.close()
    return list(answers.found)
