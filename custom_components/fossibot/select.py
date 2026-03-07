from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_ENABLE_ADVANCED_CONTROLS
from .coordinator import FossibotCoordinator

ADVANCED_SELECT_KEYS = {
    "acStandbyTime", "dcStandbyTime", "usbStandbyTime",
    "machineUnusedTime", "screenRestTime",
}

STANDBY_HOURS_OPTIONS = {
    "Never": 0, "30 min": 30, "1 hour": 60, "2 hours": 120,
    "4 hours": 240, "8 hours": 480, "12 hours": 720,
    "16 hours": 960, "24 hours": 1440,
}

USB_STANDBY_OPTIONS = {
    "Never": 0, "1 min": 1, "2 min": 2, "3 min": 3, "5 min": 5,
    "10 min": 10, "15 min": 15, "30 min": 30, "1 hour": 60,
    "2 hours": 120, "4 hours": 240,
}

MACHINE_UNUSED_OPTIONS = {
    "Never": 0, "1 min": 1, "3 min": 3, "5 min": 5, "10 min": 10,
    "15 min": 15, "30 min": 30, "1 hour": 60, "2 hours": 120,
}

SCREEN_REST_OPTIONS = {
    "Never": 0, "30 sec": 30, "1 min": 60, "3 min": 180,
    "5 min": 300, "10 min": 600, "30 min": 1800,
}

LED_OPTIONS = {
    "Off": 0, "On": 1, "SOS": 2, "Flash": 3,
}

SELECT_DEFS = [
    {"key": "acStandbyTime", "name": "AC Standby Time", "register": 60,
     "options": STANDBY_HOURS_OPTIONS, "icon": "mdi:timer-outline"},
    {"key": "dcStandbyTime", "name": "DC Standby Time", "register": 61,
     "options": STANDBY_HOURS_OPTIONS, "icon": "mdi:timer-outline"},
    {"key": "usbStandbyTime", "name": "USB Standby Time", "register": 59,
     "options": USB_STANDBY_OPTIONS, "icon": "mdi:timer-outline"},
    {"key": "machineUnusedTime", "name": "Machine Unused Auto-Off", "register": 68,
     "options": MACHINE_UNUSED_OPTIONS, "icon": "mdi:timer-off-outline"},
    {"key": "screenRestTime", "name": "Screen Rest Time", "register": 62,
     "options": SCREEN_REST_OPTIONS, "icon": "mdi:monitor-shimmer"},
    {"key": "led_mode", "name": "LED Mode", "register": 27,
     "options": LED_OPTIONS, "icon": "mdi:flashlight"},
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
        for sdef in SELECT_DEFS:
            if not enable_advanced and sdef["key"] in ADVANCED_SELECT_KEYS:
                continue
            entities.append(FossibotSelect(coordinator, sdef))
    async_add_entities(entities)


class FossibotSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FossibotCoordinator, definition: dict):
        super().__init__(coordinator)
        self._key = definition["key"]
        self._register = definition["register"]
        self._options_map = definition["options"]
        self._value_to_label = {v: k for k, v in self._options_map.items()}
        self._attr_name = definition["name"]
        self._attr_unique_id = f"{coordinator.device_mac}_{self._key}"
        self._attr_options = list(self._options_map.keys())
        self._attr_icon = definition.get("icon")

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
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._key)
        if raw is None:
            return None
        return self._value_to_label.get(raw, str(raw))

    async def async_select_option(self, option: str) -> None:
        value = self._options_map.get(option)
        if value is not None:
            await self.coordinator.async_write_register(self._register, value)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
