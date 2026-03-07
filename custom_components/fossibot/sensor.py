from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_ENABLE_ENERGY_SENSORS
from .coordinator import FossibotCoordinator

ENERGY_SENSOR_KEYS = {"pv_energy_today", "pv_energy_total", "energy_input_kwh", "energy_output_kwh"}

SENSOR_DEFS = [
    {
        "key": "battery_soc",
        "name": "Battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "icon": "mdi:battery",
        "precision": 1,
    },
    {
        "key": "total_input_power",
        "name": "Input Power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:flash",
        "precision": 0,
    },
    {
        "key": "totalOutputPower",
        "name": "Output Power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:power-plug-outline",
        "precision": 0,
    },
    {
        "key": "pv_energy_today",
        "name": "Solar Energy Today",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-power-variant",
        "precision": 2,
    },
    {
        "key": "pv_energy_total",
        "name": "Solar Energy Total",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:solar-power",
        "precision": 2,
    },
    {
        "key": "energy_input_kwh",
        "name": "Energy Charged",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-charging",
        "precision": 3,
    },
    {
        "key": "energy_output_kwh",
        "name": "Energy Consumed",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:home-lightning-bolt",
        "precision": 3,
    },
    {
        "key": "battery_voltage",
        "name": "Battery Voltage",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "icon": "mdi:sine-wave",
        "precision": 1,
    },
    {
        "key": "ambient_temp",
        "name": "Temperature",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "precision": 1,
    },
    {
        "key": "remain_charge_minutes",
        "name": "Charge Time Remaining",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
        "icon": "mdi:battery-charging",
    },
    {
        "key": "remain_discharge_hours",
        "name": "Discharge Time Remaining",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.HOURS,
        "icon": "mdi:battery-minus",
        "precision": 1,
    },
    {
        "key": "dcChargePower",
        "name": "DC Charge Power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:current-dc",
        "precision": 0,
    },
    {
        "key": "acChargePower",
        "name": "AC Charge Power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:current-ac",
        "precision": 0,
    },
    {
        "key": "pv1ChargePower",
        "name": "Solar Power",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:solar-panel",
        "precision": 0,
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    enable_energy = entry.options.get(CONF_ENABLE_ENERGY_SENSORS, True)
    entities = []
    for coordinator in data["coordinators"]:
        for sdef in SENSOR_DEFS:
            if not enable_energy and sdef["key"] in ENERGY_SENSOR_KEYS:
                continue
            entities.append(FossibotSensor(coordinator, sdef))
    async_add_entities(entities)


class FossibotSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FossibotCoordinator, definition: dict):
        super().__init__(coordinator)
        self._key = definition["key"]
        self._attr_name = definition["name"]
        self._attr_unique_id = f"{coordinator.device_mac}_{self._key}"
        self._attr_device_class = definition.get("device_class")
        self._attr_state_class = definition.get("state_class")
        self._attr_native_unit_of_measurement = definition.get("unit")
        self._attr_icon = definition.get("icon")
        if "precision" in definition:
            self._attr_suggested_display_precision = definition["precision"]

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

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)
