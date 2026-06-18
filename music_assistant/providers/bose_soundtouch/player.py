"""Bose SoundTouch Player implementation."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element

from bosesoundtouchapi import SoundTouchClient, SoundTouchDevice, SoundTouchNotifyCategorys
from bosesoundtouchapi.models import NowPlayingStatus, Volume, Zone, ZoneMember
from bosesoundtouchapi.ws import SoundTouchWebSocket
from music_assistant_models.enums import MediaType, PlaybackState, PlayerFeature
from music_assistant_models.errors import MusicAssistantError
from music_assistant_models.player import DeviceInfo, PlayerSource

from music_assistant.models.player import Player, PlayerMedia

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncServiceInfo

    from .provider import BoseSoundTouchPlayerProvider


class BoseSoundTouchPlayer(Player):
    """Bose SoundTouch Player implementation."""

    def __init__(
        self,
        provider: BoseSoundTouchPlayerProvider,
        player_id: str,
        soundtouchdevice: SoundTouchDevice,
        ip_address: str,
        info: AsyncServiceInfo | None = None,
    ) -> None:
        """Initialize Bose SoundTouch Player."""
        super().__init__(provider, player_id)
        self._soundtouchdevice = soundtouchdevice
        self._ip_address = ip_address
        self._info = info
        self._client = SoundTouchClient(soundtouchdevice)
        self._socket: SoundTouchWebSocket | None = None
        self._caps = self._client.GetCapabilities()
        self._ws_supported: bool = self._caps is not None and self._caps.IsWebSocketApiProxyCapable
        self._attr_name = self._soundtouchdevice.DeviceName
        self._attr_available = True
        self._attr_supported_features = {
            PlayerFeature.NEXT_PREVIOUS,
            PlayerFeature.PAUSE,
            PlayerFeature.PLAY_MEDIA,
            PlayerFeature.POWER,
            PlayerFeature.SEEK,
            PlayerFeature.SELECT_SOURCE,
            PlayerFeature.SET_MEMBERS,
            PlayerFeature.VOLUME_MUTE,
            PlayerFeature.VOLUME_SET,
        }
        device_info = DeviceInfo(
            model=self._soundtouchdevice.DeviceType,
            manufacturer=(
                self._info.decoded_properties.get("MANUFACTURER") or "Bose"
                if self._info
                else "Bose"
            ),
        )
        device_info.ip_address = self._soundtouchdevice.Host
        device_info.mac_address = self._soundtouchdevice.MacAddress
        self._attr_device_info = device_info
        self._set_attributes()

        # register or update player in provider
        self.mass.loop.call_soon_threadsafe(
            asyncio.create_task, self.mass.players.register_or_update(self)
        )

        # initialize websocket connection if supported
        if self._ws_supported:
            self.mass.loop.create_task(self._initialize_websocket())

    @property
    def needs_poll(self) -> bool:
        """Return if the player needs to be polled for updates."""
        return not self._ws_supported

    @property
    def poll_interval(self) -> int:
        """Return the interval in seconds to poll the player for state updates."""
        return 5 if self._attr_playback_state == PlaybackState.PLAYING else 30

    async def power(self, powered: bool) -> None:
        """Handle POWER command on the player."""
        try:
            if powered:
                self._client.PowerOn()
            else:
                self._client.PowerOff()
                self._attr_playback_state = PlaybackState.IDLE
            self._attr_powered = powered
            self.update_state()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to set power state to {powered} for player {self.player_id}: {exc}"
            ) from exc

    async def volume_set(self, volume_level: int) -> None:
        """Handle VOLUME_SET command on the player."""
        try:
            self._client.SetVolumeLevel(volume_level)
            self._attr_volume_level = volume_level
            self.update_state()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to set volume level to {volume_level} for player {self.player_id}: {exc}"
            ) from exc

    async def volume_mute(self, muted: bool) -> None:
        """Handle VOLUME_MUTE command on the player."""
        try:
            if muted:
                self._client.MuteOn()
            else:
                self._client.MuteOff()
            self._attr_volume_muted = muted
            self.update_state()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to set volume mute to {muted} for player {self.player_id}: {exc}"
            ) from exc

    async def play(self) -> None:
        """Handle PLAY command on the player."""
        try:
            self._client.MediaPlay()
            self._attr_playback_state = PlaybackState.PLAYING
            self.update_state()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to play media on player {self.player_id}: {exc}"
            ) from exc

    async def stop(self) -> None:
        """Handle STOP command on the player."""
        try:
            self._client.MediaStop()
            self._attr_playback_state = PlaybackState.IDLE
            self.update_state()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to stop media on player {self.player_id}: {exc}"
            ) from exc

    async def pause(self) -> None:
        """Handle PAUSE command on the player."""
        try:
            self._client.MediaPause()
            self._attr_playback_state = PlaybackState.PAUSED
            self.update_state()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to pause media on player {self.player_id}: {exc}"
            ) from exc

    async def next_track(self) -> None:
        """Handle NEXT command on the player."""
        try:
            self._client.MediaNextTrack()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to play next track on player {self.player_id}: {exc}"
            ) from exc

    async def previous_track(self) -> None:
        """Handle PREVIOUS command on the player."""
        try:
            self._client.MediaPreviousTrack()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to play previous track on player {self.player_id}: {exc}"
            ) from exc

    async def seek(self, position: float) -> None:
        """Handle SEEK command on the player."""
        try:
            self._client.MediaSeekToTime(int(position))
            self._attr_elapsed_time = position
            self._attr_elapsed_time_last_updated = time.time()
            self.update_state()
        except Exception as exc:
            raise MusicAssistantError(
                f"Failed to seek to position {position} on player {self.player_id}: {exc}"
            ) from exc

    async def play_media(self, media: PlayerMedia) -> None:
        """Handle playing media on the player."""
        url = await self.provider.mass.streams.resolve_stream_url(self.player_id, media)
        # Test if play media method works on the device
        try:
            self._client.PlayUrl(
                url=url,
                artist=media.artist or "",
                album=media.album or "",
                track=media.title or "",
            )
        except Exception as exc:
            self.logger.debug("Error playing media with play url method: %s", exc)
            # Fallback to select source UPNP
            try:
                self._client.PlayUrlDlna(
                    url=url,
                    artist=media.artist or "",
                    album=media.album or "",
                    track=media.title or "",
                    artUrl=media.image_url or None,
                )
            except Exception as exc2:
                self.logger.error("Error playing media with DLNA method: %s", exc2)

        self._attr_playback_state = PlaybackState.PLAYING
        self.update_state()

    async def select_source(self, source: str) -> None:
        """Select a source for the player."""
        try:
            if ":" in source:
                source_name, source_account = source.split(":", 1)
            else:
                source_name, source_account = source, ""
            self._client.SelectSource(source_name, source_account)
        except Exception as exc:
            self.logger.error("Error selecting source %s: %s", source, exc)

    async def set_members(
        self,
        player_ids_to_add: list[str] | None = None,
        player_ids_to_remove: list[str] | None = None,
    ) -> None:
        """Handle SET_MEMEBERS command on the player."""
        player_ids_to_add = player_ids_to_add or []
        player_ids_to_remove = player_ids_to_remove or []
        soundtouch_player_ids_to_add = {x for x in player_ids_to_add if not x.startswith("ap")}
        soundtouch_player_ids_to_remove = {
            x for x in player_ids_to_remove if not x.startswith("ap")
        }
        if soundtouch_player_ids_to_add or soundtouch_player_ids_to_remove:
            self.logger.debug(
                "Setting group members, adding: %s, removing: %s",
                soundtouch_player_ids_to_add,
                soundtouch_player_ids_to_remove,
            )
            try:
                zone_state = self._client.GetZoneStatus()
                self.logger.debug("Current zone state: %s", zone_state)

                members_to_add = []
                members_to_remove = []

                for player_id in soundtouch_player_ids_to_add:
                    if zone_state.MasterDeviceId:  # If current player is master add them as ZoneMember else as SoundTouchDevice
                        members_to_add.append(ZoneMember(deviceId=player_id))
                    else:
                        player = self.mass.players.get_player(player_id)
                        if player is None:
                            return
                        ip_address = player.device_info.ip_address
                        members_to_add.append(SoundTouchDevice(host=ip_address))

                for player_id in soundtouch_player_ids_to_remove:
                    members_to_remove.append(ZoneMember(deviceId=player_id))

                if (
                    zone_state.MasterDeviceId is None and members_to_add
                ):  # if no zone exists create a new zone else add members to existing zone
                    self._client.CreateZoneFromDevices(self._soundtouchdevice, members_to_add)
                else:
                    if members_to_add:
                        self._client.AddZoneMembers(members_to_add)
                    if members_to_remove:
                        self._client.RemoveZoneMembers(members_to_remove)

            except Exception as exc:
                self.logger.error("Error getting zone status: %s", exc)
                return

    async def ungroup(self) -> None:
        """Handle UNGROUP command on the player."""
        try:
            self._client.RemoveZone()
        except Exception as exc:
            self.logger.error("Error ungrouping player: %s", exc)

    async def on_unload(self) -> None:
        """Handle unload of the player."""
        if self._socket:
            self._socket.StopNotification()
            self._socket.ClearListeners()
            self._socket = None

        try:
            self._client.MediaStop()
        except Exception as exc:
            self.logger.warning("Error stopping player: %s", exc)

    def _set_attributes(self) -> None:
        """Update/set (dynamic) properties."""
        # set volume information
        volume_info = None
        try:
            volume_info = self._client.GetVolume()
        except Exception as exc:
            self.logger.warning(
                "Failed to retrieve volume information for player %s: %s", self.player_id, exc
            )
        if isinstance(volume_info, Volume):
            self._attr_volume_level = volume_info.Actual
            self._attr_volume_muted = volume_info.IsMuted

        # set source list
        self._attr_source_list = self._get_source_list()

        # update initial now playing info
        try:
            now_playing_status = self._client.GetNowPlayingStatus()
            self._update_now_playing_info(now_playing_status)
        except Exception as exc:
            self.logger.warning(
                "Failed to retrieve now playing information for player %s: %s", self.player_id, exc
            )

        # update initial zone members state
        try:
            zone_state = self._client.GetZoneStatus()
            self._update_zone_state(zone_state)
        except Exception as exc:
            self.logger.warning(
                "Failed to retrieve zone information for player %s: %s", self.player_id, exc
            )

    def _get_source_list(self) -> list[PlayerSource]:
        """Return list of available (native) sources for this player."""
        sources = []
        try:
            source_list = self._client.GetSourceList()
            for source in source_list.SourceItems:
                source_id = source.Source
                if source.SourceAccount:
                    source_id += f":{source.SourceAccount}"

                passive = source.Source.upper() in ("SPOTIFY")

                sources.append(
                    PlayerSource(
                        id=source_id,
                        name=source.SourceTitle,
                        passive=passive,
                        can_play_pause=True,
                        can_next_previous=True,
                        can_seek=True,
                    )
                )
        except Exception as exc:
            self.logger.warning(
                "Failed to retrieve source list for player %s: %s", self.player_id, exc
            )
        return sources

    def _update_zone_state(self, zone_state: Zone) -> None:
        """Update zone state information."""
        if zone_state.MasterDeviceId == self._soundtouchdevice.DeviceId:
            self._attr_group_members = [member.DeviceId for member in zone_state.Members]
        else:
            self._attr_group_members = []

        self.update_state()

    def _update_now_playing_info(self, now_playing_status: NowPlayingStatus) -> None:
        """Update now playing information based on the provided status."""
        current_media_uri = None
        current_from_mass = False  # if current media is played from mass
        if self._attr_current_media:
            current_media_uri = self._attr_current_media.uri
        if (
            now_playing_status.Source == "UPNP"
            and current_media_uri == now_playing_status.ContentItem.Location
        ):
            current_from_mass = True
        source_id = now_playing_status.Source
        if now_playing_status.SourceAccount:
            source_id += f":{now_playing_status.SourceAccount}"
        media_type = MediaType.UNKNOWN
        stream_type = now_playing_status.StreamType
        if stream_type:
            if "TRACK" in stream_type.upper():
                media_type = MediaType.TRACK
            elif "RADIO" in stream_type.upper():
                media_type = MediaType.RADIO

        if now_playing_status.ContentItem and current_from_mass is False:
            self._attr_current_media = PlayerMedia(
                uri=now_playing_status.ContentItem.Location,
                title=now_playing_status.Track,
                artist=now_playing_status.Artist,
                album=now_playing_status.Album,
                image_url=now_playing_status.ArtUrl,
                duration=now_playing_status.Duration or None,
                media_type=media_type,
            )

        if (
            current_from_mass is False
        ):  # if current media is played from mass, do not update source to prevent source switch in mass
            self._attr_active_source = source_id
        else:
            self._attr_active_source = None

        # update elapsed time if media is playing
        self._attr_elapsed_time = float(now_playing_status.Position) or None
        self._attr_elapsed_time_last_updated = time.time()

        # update player state
        play_state = now_playing_status.PlayStatus
        if play_state and play_state.upper() != "STANDBY":
            self._attr_powered = True
            if "PLAY" in play_state.upper():
                self._attr_playback_state = PlaybackState.PLAYING
            elif "PAUSE" in play_state.upper():
                self._attr_playback_state = PlaybackState.PAUSED
            else:
                self._attr_playback_state = PlaybackState.IDLE
        else:
            self._attr_powered = False
            self._attr_playback_state = PlaybackState.IDLE

        self.update_state()

    async def _initialize_websocket(self) -> None:
        """Initialize websocket connection to receive real-time updates from the device."""
        if not self._ws_supported:
            return

        try:
            self._socket = SoundTouchWebSocket(self._client, pingInterval=60)
            self._socket.AddListener(SoundTouchNotifyCategorys.WebSocketClose, self._on_ws_close)
            self._socket.AddListener(SoundTouchNotifyCategorys.WebSocketError, self._on_ws_error)
            self._socket.AddListener(
                SoundTouchNotifyCategorys.ALL, self._handle_websocket_notification
            )
            self._socket.StartNotification()
            self.logger.debug("WebSocket connection established for player %s", self.player_id)
        except Exception as exc:
            self.logger.warning(
                "Failed to establish WebSocket connection for player %s: %s", self.player_id, exc
            )

    def _on_ws_close(self, client: SoundTouchClient, ex: Exception) -> None:
        """Handle websocket close event."""
        self._attr_available = False
        self.update_state()

    def _on_ws_error(self, client: SoundTouchClient, ex: Exception) -> None:
        """Handle websocket error event."""
        self._attr_available = False
        self.update_state()

    def _handle_websocket_notification(self, client: SoundTouchClient, args: list[Element]) -> None:
        """Handle incoming websocket notifications."""
        if not args:
            return

        element = args[0]

        # update now playing information on nowPlaying notifications
        if getattr(element, "tag", None) == "nowPlaying":
            try:
                now_playing_status = NowPlayingStatus(root=element)
                self.mass.loop.call_soon_threadsafe(
                    self._update_now_playing_info, now_playing_status
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to parse now playing status from WebSocket notification for player %s: %s",
                    self.player_id,
                    exc,
                )

        # update volume information on volume notifications
        elif getattr(element, "tag", None) == "volume":
            try:
                volume_info = Volume(root=element)

                def _update_volume() -> None:
                    self._attr_volume_level = getattr(volume_info, "Actual", None)
                    self._attr_volume_muted = getattr(volume_info, "IsMuted", None)
                    self.update_state()

                self.mass.loop.call_soon_threadsafe(_update_volume)
            except Exception as exc:
                self.logger.warning(
                    "Failed to parse volume information from WebSocket notification for player %s: %s",
                    self.player_id,
                    exc,
                )

        # update zone information on zone notifications
        elif getattr(element, "tag", None) == "zone":
            try:
                zone_state = Zone(root=element)
                self.mass.loop.call_soon_threadsafe(self._update_zone_state, zone_state)
            except Exception as exc:
                self.logger.warning(
                    "Failed to parse zone information from WebSocket notification for player %s: %s",
                    self.player_id,
                    exc,
                )
