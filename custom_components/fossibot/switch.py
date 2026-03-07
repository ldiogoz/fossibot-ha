from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_ENABLE_ADVANCED_CONTROLS
from .coordinator import FossibotCoordinator

ADVANCED_SWITCH_KEYS = {"key_sound", "silent_charging", "low_batt_notify_enabled"}

SWITCH_DEFS = [
    {"key": "ac_on", "name": "AC Output", "register": 26, "icon": "mdi:power-plug"},
    {"key": "dc_on", "name": "DC Output", "register": 25, "icon": "mdi:current-dc"},
    {"key": "usb_on", "name": "USB Output", "register": 24, "icon": "mdi:usb"},
    {"key": "key_sound", "name": "Key Sound", "register": 56, "icon": "mdi:volume-high"},
    {"key": "silent_charging", "name": "Silent Charging", "register": 57, "icon": "mdi:volume-off"},
    {"key": "low_batt_notify_enabled", "name": "Low Battery Notification", "register": 84,
     "icon": "mdi:battery-alert", "packed": True, "packed_byte": "high"},
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    enable_advanced = entry.options.get(CONF_ENABLE_ADVANCED_CONTROLS, True)
    entities = []
    for coordinator in data["coordinators"]:
        for sdef in SWITCH_DEFS:
            if not enable_advanced and sdef["key"] in ADVANCED_SWITCH_KEYS:
                continue
            entities.append(FossibotSwitch(coordinator, sdef))
    async_add_entities(entities)


class FossibotSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FossibotCoordinator, definition: dict):
        super().__init__(coordinator)
        self._key = definition["key"]
        self._register = definition["register"]
        self._attr_name = definition["name"]
        self._attr_unique_id = f"{coordinator.device_mac}_{self._key}"
        self._attr_icon = definition.get("icon")
        self._packed = definition.get("packed", False)
        self._packed_byte = definition.get("packed_byte")

    @property
    def device_info(self) -> DeviceInfo:
        info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_mac)},
            name=self.coordinator.device_name,
            manufacturer="Fossibot",
            model=self.coordinator.device_model,
        )
        if self.coordinator.sw_version:
            info["sw_version"] = self.coordinator.sw_version
        if self.coordinator.hw_version:
            info["hw_version"] = self.coordinator.hw_version
        return info

    @property
    def available(self) -> bool:
        return self.coordinator.device_available

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key, False)

    async def async_turn_on(self, **kwargs) -> None:
        if self._packed:
            await self._write_packed(True)
        else:
            await self.coordinator.async_write_register(self._register, 1)

    async def async_turn_off(self, **kwargs) -> None:
        if self._packed:
            await self._write_packed(False)
        else:
            await self.coordinator.async_write_register(self._register, 0)

    async def _write_packed(self, enabled: bool):
        threshold = self.coordinator.data.get("low_batt_notify_threshold", 10)
        val = ((1 if enabled else 0) << 8) | threshold
        await self.coordinator.async_write_register(self._register, val)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
