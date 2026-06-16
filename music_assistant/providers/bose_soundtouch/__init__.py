"""
Bose SoundTouch Player provider for Music Assistant.

Based on the bosesoundtouchapi library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_assistant.constants import CONF_ENTRY_MANUAL_DISCOVERY_IPS

from .provider import BoseSoundTouchPlayerProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigEntry, ProviderConfig
    from music_assistant_models.provider import ProviderManifest

    from music_assistant.mass import MusicAssistant
    from music_assistant.models import ProviderInstanceType


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    return BoseSoundTouchPlayerProvider(mass, manifest, config)


async def get_config_entries() -> tuple[ConfigEntry, ...]:
    """Return Config entries to setup this provider."""
    return (CONF_ENTRY_MANUAL_DISCOVERY_IPS,)
