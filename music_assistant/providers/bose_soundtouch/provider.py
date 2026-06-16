"""
Bose SoundTouch provider for Music Assistant.

Based on the bosesoundtouchapi library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bosesoundtouchapi import SoundTouchDevice
from zeroconf import ServiceStateChange

from music_assistant.constants import (
    CONF_ENTRY_MANUAL_DISCOVERY_IPS,
)
from music_assistant.helpers.util import get_primary_ip_address_from_zeroconf
from music_assistant.models.player_provider import PlayerProvider

from .helpers import extract_player_id
from .player import BoseSoundTouchPlayer

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncServiceInfo


class BoseSoundTouchPlayerProvider(PlayerProvider):
    """Bose SoundTouch Player provider."""

    async def handle_async_init(self) -> None:
        """Handle async initialization of the provider."""
        await super().handle_async_init()

        # handle config option for manual inserted IP's
        raw_ips = self.config.get_value(CONF_ENTRY_MANUAL_DISCOVERY_IPS.key)
        manual_ip_config: list[str] = []
        if isinstance(raw_ips, list):
            manual_ip_config = [
                str(ip).strip() for ip in raw_ips if isinstance(ip, (str, int, float))
            ]
        elif isinstance(raw_ips, (str, int, float)):
            manual_ip_config = [str(raw_ips).strip()]
        else:
            manual_ip_config = []

        for ip_address in manual_ip_config:
            try:
                soundtouchdevice = SoundTouchDevice(ip_address)
            except Exception as exc:
                self.logger.warning(
                    "Failed to connect to manually configured Bose SoundTouch device %s: %s",
                    ip_address,
                    exc,
                )
                continue
            player_id = soundtouchdevice.MacAddress.replace(":", "").lower()
            BoseSoundTouchPlayer(self, player_id, soundtouchdevice, ip_address)

    async def on_mdns_service_state_change(
        self, name: str, state_change: ServiceStateChange, info: AsyncServiceInfo | None
    ) -> None:
        """Handle mDNS service state changes."""
        if state_change != ServiceStateChange.Added or info is None:
            return

        if info.type != "_soundtouch._tcp.local.":
            return

        ip_address = get_primary_ip_address_from_zeroconf(info)
        if ip_address is None:
            self.logger.warning(
                "Could not determine IP address for Bose SoundTouch device %s",
                name,
            )
            return

        player_id = extract_player_id(info)
        if player_id is None:
            self.logger.warning(
                "Could not extract player ID from mDNS name %s for Bose SoundTouch device",
                name,
            )
            return

        # setup soundtouch device and player
        try:
            soundtouchdevice = SoundTouchDevice(host=ip_address, port=info.port or 8090)
        except Exception as exc:
            self.logger.warning(
                "Failed to connect to Bose SoundTouch device %s at %s: %s",
                name,
                ip_address,
                exc,
            )
            return

        BoseSoundTouchPlayer(self, player_id, soundtouchdevice, ip_address, info)
