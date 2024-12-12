"""Home Assistant MZC-66 integration."""
from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import ConfigSource, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant import config_entries, core, exceptions

from serial import SerialException

from .pyspeakercraft import get_speakercraft
from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

_LOGGER = logging.getLogger(__name__)

@core.callback
def translate_config_amp(prefix: str, entry: ConfigSource) -> {}:
    port = entry.data[prefix + "_port"]
    sources = []
    zones = []

    for k, v in entry.data.items():
        result = re.search(prefix + r"_source(\d)", k)
        if result:
            sources.append({"index": int(result.group(1)), "name": v})
        result = re.search(prefix + r"_zone(\d)", k)
        if result:
            zones.append({"index": int(result.group(1)), "name": v})

    return {"port": port, "sources": sources, "zones": zones}


@core.callback
def translate_config_amps(entry: ConfigEntry) -> [{}]:
    if "amps" in entry.data:
        return entry.data["amps"]

    amps = []
    amps.append(translate_config_amp("amp1", entry))
    amps.append(translate_config_amp("amp2", entry))
    return amps


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Speakercraft MZC-66 Integration from a config entry."""
    try:
        amps_config = translate_config_amps(entry)
        hass.config_entries.async_update_entry(entry, data={"amps": amps_config})
        hass.data.setdefault(DOMAIN, {})
        hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    except SerialException as err:
        _LOGGER.error("Error connecting to Speakercraft controller")
        raise ConfigEntryNotReady from err

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
