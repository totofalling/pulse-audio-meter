from __future__ import annotations
import logging
import asyncio
from datetime import timedelta
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

DOMAIN = "pulse_audio_meter"
API = "http://homeassistant.local:8765"
PLATFORMS = ["sensor", "number", "switch"]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp.ClientSession()
    async def update():
        try:
            async with session.get(f"{API}/state", timeout=aiohttp.ClientTimeout(total=2)) as r:
                if r.status != 200:
                    raise UpdateFailed(f"HTTP {r.status}")
                return await r.json()
        except Exception as e:
            raise UpdateFailed(str(e)) from e
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="PulseAudio Meter", update_method=update,
        update_interval=timedelta(seconds=0.5),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = (coordinator, session)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register the Lovelace card automatically.
    try:
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        resources = hass.data.get("lovelace", {}).get("resources")

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
    except Exception:
        logging.getLogger(__name__).exception(
            "Unable to register PulseAudio Meter Lovelace resource"
        )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data[DOMAIN].pop(entry.entry_id)
    coordinator, session = data
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await session.close()
    return True
