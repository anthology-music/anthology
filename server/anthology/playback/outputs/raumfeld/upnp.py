"""UPnP control as the Raumfeld adapter needs it: device descriptions and SOAP actions
(UPnP Device Architecture 1.0). Descriptions and answers come from devices on the local
network; they are parsed with the standard library, which resolves no external entities and
whose expat limits entity expansion."""

from dataclasses import dataclass
from urllib.parse import urljoin
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import httpx

from anthology.playback.outputs.base import OutputError

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
DEVICE_NS = "urn:schemas-upnp-org:device-1-0"
CONTROL_NS = "urn:schemas-upnp-org:control-1-0"
AV_TRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
RENDERING_CONTROL = "urn:schemas-upnp-org:service:RenderingControl:1"
CONNECTION_MANAGER = "urn:schemas-upnp-org:service:ConnectionManager:1"


def parse(text: str | bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(text)  # noqa: S314 (see the module docstring)
    except ElementTree.ParseError as error:
        raise OutputError(f"invalid XML: {error}") from error


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass(frozen=True)
class Device:
    udn: str
    name: str
    # Service type → absolute control URL.
    controls: dict[str, str]


def device(location: str, text: str | bytes) -> Device:
    """The root device of a description document."""
    root = parse(text)
    ns = {"d": DEVICE_NS}
    base = root.findtext("d:URLBase", default="", namespaces=ns) or location
    node = root.find("d:device", ns)
    if node is None:
        raise OutputError("description without a device")
    controls = {}
    for service in node.iterfind("d:serviceList/d:service", ns):
        kind = service.findtext("d:serviceType", default="", namespaces=ns)
        control = service.findtext("d:controlURL", default="", namespaces=ns)
        if kind and control:
            controls[kind] = urljoin(base, control)
    return Device(
        udn=node.findtext("d:UDN", default="", namespaces=ns),
        name=node.findtext("d:friendlyName", default="", namespaces=ns),
        controls=controls,
    )


def envelope(service: str, action: str, arguments: dict[str, str | int]) -> str:
    body = "".join(f"<{key}>{escape(str(value))}</{key}>" for key, value in arguments.items())
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_ENV}" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>'
    )


async def call(
    client: httpx.AsyncClient,
    control_url: str,
    service: str,
    action: str,
    arguments: dict[str, str | int],
) -> dict[str, str]:
    """Run one action; returns the output arguments. Raises ``OutputError``."""
    headers = {
        "SOAPACTION": f'"{service}#{action}"',
        "Content-Type": 'text/xml; charset="utf-8"',
    }
    try:
        response = await client.post(
            control_url, content=envelope(service, action, arguments), headers=headers
        )
    except httpx.HTTPError as error:
        raise OutputError(f"{action}: {error.__class__.__name__}") from error
    if response.status_code != 200:
        code = None
        if response.content:
            try:
                code = parse(response.content).findtext(f".//{{{CONTROL_NS}}}errorCode")
            except OutputError:
                pass
        raise OutputError(f"{action}: HTTP {response.status_code}, UPnP error {code}")
    body = parse(response.content).find(f"{{{SOAP_ENV}}}Body")
    answer = next(iter(body), None) if body is not None else None
    if answer is None:
        raise OutputError(f"{action}: empty answer")
    return {local(child.tag): child.text or "" for child in answer}
