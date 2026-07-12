"""Helpers for the Bose SoundTouch Player Provider."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from bosesoundtouchapi.models.productcechdmimodes import ProductCecHdmiModes
from music_assistant_models.config_entries import ConfigValueOption
from music_assistant_models.enums import MediaType
from music_assistant_models.errors import MusicAssistantError

from music_assistant import MusicAssistant

if TYPE_CHECKING:
    from music_assistant_models.media_items import SearchResults
    from zeroconf.asyncio import AsyncServiceInfo

PRESET_IDS = range(1, 7)
SEARCH_RESULT_LIMIT = 25
SEARCH_TIMEOUT = 10

SEARCHABLE_MEDIA_TYPES = (
    MediaType.ARTIST,
    MediaType.ALBUM,
    MediaType.TRACK,
    MediaType.PLAYLIST,
    MediaType.RADIO,
)

MEDIA_TYPE_OPTIONS = [
    ConfigValueOption(title=mt.value.title(), value=mt.value) for mt in SEARCHABLE_MEDIA_TYPES
]


def extract_player_id(info: AsyncServiceInfo) -> str | None:
    """
    Fetch 'MAC' from info.decoded_properties and normalize it to a cleaned str.

    Returns None if no valid ID is present.
    """
    props: Mapping[str, str | None] = info.decoded_properties

    mac_str: str | None = None

    # Prefer the str key "MAC"
    mac_value_str = props.get("MAC")
    if isinstance(mac_value_str, str):
        mac_str = mac_value_str.strip()

    # Support bytes key b"MAC"
    if mac_str is None:
        props_any: Mapping[Any, Any] = cast("Mapping[Any, Any]", props)
        mac_value_bytes = props_any.get(b"MAC")
        if isinstance(mac_value_bytes, bytes):
            mac_str = mac_value_bytes.decode("utf-8", errors="ignore").strip()

    return mac_str or None


async def _build_media_options(
    mass: MusicAssistant,
    media_type: MediaType,
    query: str,
    selected_media: str | None,
    refresh: bool,
) -> list[ConfigValueOption]:
    options: list[ConfigValueOption] = []

    if refresh:
        for item in await _search_media(mass, media_type, query):
            if item.uri:
                options.append(
                    ConfigValueOption(
                        title=f"{item.name} ({item.media_type.value})",
                        value=item.uri,
                    )
                )

    # Add selected media if not present
    if selected_media and selected_media not in {o.value for o in options}:
        options.append(ConfigValueOption(title=selected_media, value=selected_media))

    return sorted(options, key=lambda o: (o.title or "").lower())


async def _search_media(
    mass: MusicAssistant,
    media_type: MediaType,
    query: str,
) -> list[Any]:
    if not query:
        return []

    try:
        result: SearchResults = await asyncio.wait_for(
            mass.music.search(
                search_query=query,
                media_types=[media_type],
                limit=SEARCH_RESULT_LIMIT,
                library_only=False,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except MusicAssistantError, TimeoutError:
        return []

    match media_type:
        case MediaType.TRACK:
            return list(result.tracks)
        case MediaType.ALBUM:
            return list(result.albums)
        case MediaType.ARTIST:
            return list(result.artists)
        case MediaType.PLAYLIST:
            return list(result.playlists)
        case MediaType.RADIO:
            return list(result.radio)
        case _:
            return []


def _str(values: dict[str, Any], key: str, default: str = "") -> str:
    val = values.get(key)
    return val if isinstance(val, str) else default


def _media_type_from_config(
    values: dict[str, Any],
    key: str,
    default: MediaType = MediaType.PLAYLIST,
) -> MediaType:
    if not values:
        return default
    try:
        raw = values.get(key, default.value)
        mt = MediaType(raw)
        return mt if mt in SEARCHABLE_MEDIA_TYPES else default
    except ValueError:
        return default


def _get_hdmi_cec_modes_options() -> list[ConfigValueOption]:
    options: list[ConfigValueOption] = []

    for member in ProductCecHdmiModes:
        options.append(
            ConfigValueOption(
                title=member.name.replace("_", " ").title(),
                value=member.value,
            )
        )

    return sorted(options, key=lambda o: (o.title or "").lower())
