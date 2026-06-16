"""
Bose SoundTouch Player provider for Music Assistant.

Based on the bosesoundtouchapi library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_assistant.constants import CONF_ENTRY_MANUAL_DISCOVERY_IPS

from .provider import BoseSoundTouchPlayerProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigEntry, ConfigValueType, ProviderConfig
    from music_assistant_models.provider import ProviderManifest

    from music_assistant.mass import MusicAssistant
    from music_assistant.models import ProviderInstanceType


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize provider(instance) with given configuration."""
    return BoseSoundTouchPlayerProvider(mass, manifest, config)


async def get_config_entries(
    _mass: MusicAssistant,
    _instance_id: str | None = None,
    _action: str | None = None,
    _values: dict[str, ConfigValueType] | None = None,
) -> tuple[ConfigEntry, ...]:
    """Return Config entries to setup this provider."""
    return (CONF_ENTRY_MANUAL_DISCOVERY_IPS,)
