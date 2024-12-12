"""Support for interfacing with Speakercraft MZC-66 zone home audio controller."""
import logging
import voluptuous as vol
from typing import Any, Callable, Dict, Optional

from homeassistant import core
from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import (
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.media_player import PLATFORM_SCHEMA
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform, service
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

from .const import (
    DOMAIN,
    SERVICE_RESTORE,
    SERVICE_SNAPSHOT,
)

from .pyspeakercraft import get_speakercraft

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

SUPPORTED_FUNCTIONS = (
    SUPPORT_VOLUME_MUTE
    | SUPPORT_VOLUME_SET
    | SUPPORT_VOLUME_STEP
    | SUPPORT_TURN_ON
    | SUPPORT_TURN_OFF
    | SUPPORT_SELECT_SOURCE
)

AMP_SCHEMA = vol.Schema(
    {
        vol.Required("port"): cv.string,
        vol.Required("zones"): vol.All(cv.ensure_list, [cv.string]),
        vol.Required("sources"): vol.All(cv.ensure_list, [cv.string]),
    }
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required("amps"): vol.All(cv.ensure_list, [AMP_SCHEMA])}
)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the sensor platform."""
    entities = []
    for amp_config in config["amps"]:
        port = amp_config["port"]
        sources = amp_config["sources"]
        amp = await hass.async_add_executor_job(get_speakercraft, port)

        zone_id = 0
        for zone_config in amp_config["zones"]:
            _LOGGER.info("Adding zone %s for port %s", zone_config, port)
            zone = SpeakercraftZone(amp, sources, port, zone_id, zone_config)
            entities.append(zone)
            zone_id = zone_id + 1

    async_add_entities(entities, True)


class SpeakercraftZone(MediaPlayerEntity):
    """Representation of a Speakercraft amplifier zone."""

    def __init__(self, speakercraft, sources, port, zone_id, zone_name):
        """Initialize new zone."""
        self._speakercraft = speakercraft
        self._sources = sources
        self._zone_id = zone_id
        self._name = zone_name
        self._port = port
        self._unique_id = f"speakercraft_{self._port}_{self._zone_id}"

        self._snapshot = None
        self._state = None
        self._volume = None
        self._source = None
        self._mute = None

    def update(self):
        # """Retrieve latest state."""
        if self._speakercraft == None:
            return False

        _LOGGER.info(f"Checking status for zone {self._name}")
        state = self._speakercraft.zone_status(self._zone_id)
        _LOGGER.debug(state)

        if not state:
            return False
        self._state = STATE_ON if state.power else STATE_OFF
        self._volume = state.volume
        self._mute = state.mute

        if state.source < len(self._sources):
            self._source = self._sources[state.source]
        else:
            self._source = None
        return True

    @property
    def entity_registry_enabled_default(self):
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._zone_id <= 6

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer="Speakercraft",
            model="Zone Amplifier",
            name=self.name,
        )

    @property
    def unique_id(self):
        """Return unique ID for this device."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the zone."""
        return self._name

    @property
    def state(self):
        """Return the state of the zone."""
        return self._state

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        if self._volume is None:
            return None
        return self._volume / 100

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._mute

    @property
    def supported_features(self):
        """Return flag of media commands that are supported."""
        return SUPPORTED_FUNCTIONS

    @property
    def media_title(self):
        """Return the current source as medial title."""
        return self._source

    @property
    def source(self):
        """Return the current input source of the device."""
        return self._source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._sources

    def snapshot(self):
        """Save zone's current state."""
        if self._speakercraft != None:
            self._snapshot = self._speakercraft.zone_status(self._zone_id)

    def restore(self):
        """Restore saved state."""
        if self._snapshot and self._speakercraft != None:
            self._speakercraft.restore_zone(self._snapshot)
            self.schedule_update_ha_state(True)

    def select_source(self, source):
        """Set input source."""
        if source not in self._sources:
            return
        source_id = self._sources.index(source)

        if self._speakercraft != None:
            self._speakercraft.set_source(self._zone_id, source_id)

    def turn_on(self):
        """Turn the media player on."""
        if self._speakercraft != None:
            self._speakercraft.set_power(self._zone_id, True)

    def turn_off(self):
        """Turn the media player off."""
        if self._speakercraft != None:
            self._speakercraft.set_power(self._zone_id, False)

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        if self._speakercraft != None:
            self._speakercraft.set_mute(self._zone_id, mute)

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        if self._speakercraft != None:
            self._speakercraft.set_volume(self._zone_id, int(volume * 100))

    def volume_up(self):
        """Volume up the media player."""
        if self._volume is None:
            return

        if self._speakercraft != None:
            self._speakercraft.set_volume(self._zone_id, min(self._volume + 1, 100))

    def volume_down(self):
        """Volume down media player."""
        if self._volume is None:
            return

        if self._speakercraft != None:
            self._speakercraft.set_volume(self._zone_id, max(self._volume - 1, 0))
