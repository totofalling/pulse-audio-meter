import logging
from datetime import timedelta

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

DOMAIN = "pulse_audio_meter"
API = "http://127.0.0.1:8765"

PLATFORMS = [
    "sensor",
    "number",
    "switch",
]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up PulseAudio Meter."""
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up PulseAudio Meter."""
    session = ClientSession()

    async def update():
        """Get current PulseAudio state."""
        async with session.get(
            f"{API}/state",
            timeout=5,
        ) as response:
            response.raise_for_status()
            return await response.json()

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="PulseAudio Meter",
        update_method=update,
        update_interval=timedelta(seconds=0.5),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = (
        coordinator,
        session,
    )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )
    # Register the Lovelace card automatically.
    try:
        from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        lovelace = hass.data.get(LOVELACE_DOMAIN)

        if lovelace is not None:
            resources = getattr(lovelace, "resources", None)

            if isinstance(resources, ResourceStorageCollection):
                resource_url = "/local/pulse-audio-meter.js"

                if not any(
                    getattr(item, "url", None) == resource_url
                    for item in resources.async_items()
                ):
                    await resources.async_create_item(
                        {
                            "res_type": "module",
                            "url": resource_url,
                        }
                    )

                    _LOGGER.info(
                        "PulseAudio Meter Lovelace resource registered"
                    )
            else:
                _LOGGER.warning(
                    "Lovelace resources collection not available"
                )
        else:
            _LOGGER.warning(
                "Lovelace component not available"
            )

    except Exception:
        _LOGGER.exception(
            "Unable to register PulseAudio Meter Lovelace resource"
        )

    return True

async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload PulseAudio Meter."""
    coordinator, session = hass.data[DOMAIN].pop(entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    await session.close()

    return unload_ok
