from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_ENABLE_ADVANCED_CONTROLS
from .coordinator import FossibotCoordinator

ADVANCED_NUMBER_KEYS = {"low_batt_notify_threshold"}

NUMBER_DEFS = [
    {
        "key": "dischargeLimitx10", "name": "Discharge Limit", "register": 66,
        "min": 0, "max": 50, "step": 1, "unit": PERCENTAGE,
        "icon": "mdi:battery-arrow-down", "scale": 10, "mode": NumberMode.SLIDER,
    },
    {
        "key": "chargeLimitx10", "name": "Charge Limit", "register": 67,
        "min": 60, "max": 100, "step": 1, "unit": PERCENTAGE,
        "icon": "mdi:battery-arrow-up", "scale": 10, "mode": NumberMode.SLIDER,
    },
    {
        "key": "low_batt_notify_threshold", "name": "Low Battery Threshold", "register": 84,
        "min": 5, "max": 50, "step": 1, "unit": PERCENTAGE,
        "icon": "mdi:battery-alert-variant-outline", "scale": 1, "mode": NumberMode.BOX,
        "packed": True,
    },
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
        for ndef in NUMBER_DEFS:
            if not enable_advanced and ndef["key"] in ADVANCED_NUMBER_KEYS:
                continue
            entities.append(FossibotNumber(coordinator, ndef))
    async_add_entities(entities)


class FossibotNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FossibotCoordinator, definition: dict):
        super().__init__(coordinator)
        self._key = definition["key"]
        self._register = definition["register"]
        self._scale = definition.get("scale", 1)
        self._packed = definition.get("packed", False)
        self._attr_name = definition["name"]
        self._attr_unique_id = f"{coordinator.device_mac}_{self._key}"
        self._attr_native_min_value = definition["min"]
        self._attr_native_max_value = definition["max"]
        self._attr_native_step = definition["step"]
        self._attr_native_unit_of_measurement = definition.get("unit")
        self._attr_icon = definition.get("icon")
        self._attr_mode = definition.get("mode", NumberMode.SLIDER)

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
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._key)
        if raw is None:
            return None
        if self._scale != 1 and not self._packed:
            return round(raw / self._scale)
        return raw

    async def async_set_native_value(self, value: float) -> None:
        int_val = int(value)
        if self._packed:
            enabled = self.coordinator.data.get("low_batt_notify_enabled", False)
            write_val = ((1 if enabled else 0) << 8) | int_val
            await self.coordinator.async_write_register(self._register, write_val)
        else:
            await self.coordinator.async_write_register(self._register, int_val * self._scale)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
