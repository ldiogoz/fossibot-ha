import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FossibotApi, FossibotAuthError, FossibotApiError
from .const import DOMAIN, PLATFORMS, CONF_POLL_INTERVAL, POLL_INTERVAL, CONF_CONNECTION_TYPE, CONF_BLE_ADDRESS, CONNECTION_TYPE_BLE
from .coordinator import FossibotCoordinator
from .ble_coordinator import FossibotBleCoordinator

_LOGGER = logging.getLogger(__name__)

type FossibotConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: FossibotConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = FossibotApi(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session=session,
    )
    try:
        await api.login()
        devices = await api.get_devices()
    except FossibotAuthError as e:
        _LOGGER.error("Authentication failed: %s", e)
        raise ConfigEntryNotReady(f"Authentication failed: {e}") from e
    except (FossibotApiError, Exception) as e:
        _LOGGER.error("Failed to connect to Fossibot API: %s", e)
        raise ConfigEntryNotReady(f"Connection failed: {e}") from e

    if not devices:
        _LOGGER.warning("No Fossibot devices found")
        raise ConfigEntryNotReady("No devices found")

    poll_interval = entry.options.get(CONF_POLL_INTERVAL, POLL_INTERVAL)
    connection_type = entry.options.get(CONF_CONNECTION_TYPE, "mqtt")
    ble_address = entry.options.get(CONF_BLE_ADDRESS, "")

    coordinators: list[FossibotCoordinator | FossibotBleCoordinator] = []
    for dev in devices:
        if connection_type == CONNECTION_TYPE_BLE and ble_address:
            coordinator = FossibotBleCoordinator(hass, dev, ble_address, poll_interval=poll_interval)
            coordinator.api = api
        else:
            coordinator = FossibotCoordinator(hass, api, dev, poll_interval=poll_interval)
        try:
            await coordinator.async_connect()
        except Exception as e:
            conn_label = "BLE" if connection_type == CONNECTION_TYPE_BLE else "MQTT"
            _LOGGER.error("Failed to connect %s for device %s: %s",
                          conn_label, dev.get("name", "unknown"), e)
            raise ConfigEntryNotReady(f"{conn_label} connection failed: {e}") from e
        coordinators.append(coordinator)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinators": coordinators,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _LOGGER.info("Fossibot integration loaded with %d device(s)", len(coordinators))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: FossibotConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FossibotConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        for coordinator in entry_data.get("coordinators", []):
            try:
                await coordinator.async_disconnect()
            except Exception:
                _LOGGER.debug("Error disconnecting coordinator", exc_info=True)
    return unload_ok
