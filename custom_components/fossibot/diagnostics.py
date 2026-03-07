from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinators = entry_data.get("coordinators", [])

    devices = []
    for coord in coordinators:
        devices.append({
            "device_name": coord.device_name,
            "device_mac": coord.device_mac,
            "device_model": coord.device_model,
            "sw_version": coord.sw_version,
            "hw_version": coord.hw_version,
            "mqtt_connected": coord.connected,
            "device_available": coord.device_available,
            "poll_interval": coord._poll_interval,
            "last_response_time": coord._last_response_time,
            "energy_input_kwh": coord._energy_input_kwh,
            "energy_output_kwh": coord._energy_output_kwh,
            "data_keys": sorted(coord._data.keys()) if coord._data else [],
            "data_snapshot": {
                k: v for k, v in (coord._data or {}).items()
                if k not in ("energy_input_kwh", "energy_output_kwh")
            },
        })

    return {
        "entry_id": entry.entry_id,
        "options": dict(entry.options),
        "device_count": len(devices),
        "devices": devices,
    }
