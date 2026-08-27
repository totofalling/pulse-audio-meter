import logging
from datetime import timedelta

from aiohttp import ClientSession, web

from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.http import HomeAssistantView

DOMAIN = "pulse_audio_meter"
API = "http://127.0.0.1:8765"

PLATFORMS = [
    "sensor",
    "number",
    "switch",
]

_LOGGER = logging.getLogger(__name__)


class PulseAudioMeterStateView(HomeAssistantView):
    """Proxy PulseAudio Meter state through Home Assistant."""

    url = "/api/pulse_audio_meter/state"
    name = "api:pulse_audio_meter:state"
    requires_auth = True

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request):
        """Return current PulseAudio state."""
        session = async_get_clientsession(self.hass)

        try:
            async with session.get(
                f"{API}/state",
                timeout=5,
            ) as response:
                text = await response.text()

                return web.Response(
                    status=response.status,
                    text=text,
                    content_type="application/json",
                )

        except Exception as err:
            _LOGGER.error(
                "Unable to get PulseAudio state: %s",
                err,
            )
            return web.json_response(
                {"error": str(err)},
                status=502,
            )


class PulseAudioMeterControlView(HomeAssistantView):
    """Proxy PulseAudio Meter controls through Home Assistant."""

    url = "/api/pulse_audio_meter/control"
    name = "api:pulse_audio_meter:control"
    requires_auth = True

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request):
        """Send a control command to PulseAudio Meter."""
        session = async_get_clientsession(self.hass)

        try:
            data = await request.json()

            async with session.post(
                f"{API}/control",
                json=data,
                timeout=5,
            ) as response:
                text = await response.text()

                return web.Response(
                    status=response.status,
                    text=text,
                    content_type="application/json",
                )

        except Exception as err:
            _LOGGER.error(
                "Unable to control PulseAudio Meter: %s",
                err,
            )
            return web.json_response(
                {"error": str(err)},
                status=502,
            )


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    """Set up PulseAudio Meter."""

    hass.http.register_view(
        PulseAudioMeterStateView(hass),
    )

    hass.http.register_view(
        PulseAudioMeterControlView(hass),
    )

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
