from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FossibotCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for coordinator in data["coordinators"]:
        entities.append(FossibotShutdownButton(coordinator))
        entities.append(FossibotRefreshButton(coordinator))
    async_add_entities(entities)


class FossibotShutdownButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Remote Shutdown"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: FossibotCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_mac}_remote_shutdown"

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

    async def async_press(self) -> None:
        await self.coordinator.async_write_register(64, 1)


class FossibotRefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Refresh Data"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: FossibotCoordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_mac}_refresh"

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

    async def async_press(self) -> None:
        await self.coordinator._async_poll_once()
