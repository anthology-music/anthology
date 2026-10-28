"""DIDL-Lite metadata of a track (ContentDirectory 1.0, as renderers expect it with
``SetAVTransportURI``): the tags of the track's context, so that the system shows the album
the track is played from (spec: playback, Raumfeld support, Metadata on speakers)."""

from xml.sax.saxutils import escape, quoteattr

from anthology.playback.outputs.base import TrackMetadata


def duration(milliseconds: int) -> str:
    seconds, rest = divmod(max(milliseconds, 0), 1000)
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}.{rest:03d}"


def didl(uri: str, metadata: TrackMetadata) -> str:
    number = (
        f"<upnp:originalTrackNumber>{metadata.track_number}</upnp:originalTrackNumber>"
        if metadata.track_number
        else ""
    )
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="anthology" parentID="-1" restricted="1">'
        f"<dc:title>{escape(metadata.title)}</dc:title>"
        f"<dc:creator>{escape(metadata.artist)}</dc:creator>"
        f"<upnp:artist>{escape(metadata.artist)}</upnp:artist>"
        f"<upnp:album>{escape(metadata.album)}</upnp:album>"
        f'<upnp:artist role="AlbumArtist">{escape(metadata.album_artist)}</upnp:artist>'
        f"{number}"
        "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
        f"<res protocolInfo={quoteattr(f'http-get:*:{metadata.mime_type}:*')} "
        f'duration="{duration(metadata.duration_ms)}">{escape(uri)}</res>'
        "</item></DIDL-Lite>"
    )
