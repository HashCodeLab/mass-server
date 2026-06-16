"""Helpers for the Bose SoundTouch Player Provider."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncServiceInfo


def extract_player_id(info: AsyncServiceInfo) -> str | None:
    """
    Fetch 'MAC' from info.decoded_properties and normalize it to a cleaned str.

    Returns None if no valid ID is present.
    """
    props = info.decoded_properties  # declared as dict[str, str | None]

    mac_str: str | None = None

    # 1) Prefer the str key "MAC" (type is str | None by annotation)
    mac_value_str = props.get("MAC")
    if mac_value_str is not None:
        # mac_value_str is guaranteed to be str here
        mac_str = mac_value_str.strip()

    # 2) Optionally support a bytes key b"MAC" via a widened Mapping[Any, Any]
    if mac_str is None:
        props_any: Mapping[Any, Any] = cast("Mapping[Any, Any]", props)
        mac_value_bytes = props_any.get(b"MAC")
        if isinstance(mac_value_bytes, bytes):
            mac_str = mac_value_bytes.decode("utf-8", errors="ignore").strip()

    return mac_str or None
