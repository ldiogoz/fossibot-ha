import asyncio
import logging
import time
from typing import Any

from bleak import BleakClient, BleakScanner
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, POLL_INTERVAL, CAPACITY_WH, BLE_SERVICE_UUID, BLE_WRITE_UUID, BLE_NOTIFY_UUID
from .modbus import crc16_modbus, build_read_request, build_write_request, parse_response

_LOGGER = logging.getLogger(__name__)

BLE_DEVICE_PREFIXES = ("POWER-", "Socket-", "Meter-", "DC_DC-")


class FossibotBleCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, device: dict, ble_address: str, poll_interval: int = POLL_INTERVAL):
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=None,
        )
        self.device = device
        self._ble_address = ble_address
        self._ble_client: BleakClient | None = None
        self._modbus_addr = device.get("modbus_address", 17)
        self._modbus_count = device.get("modbus_count", 80)
        self._poll_interval = poll_interval
        self._poll_task: asyncio.Task | None = None
        self._connected = False
        self._intentional_disconnect = False
        self._reconnect_task: asyncio.Task | None = None
        self._data: dict[str, Any] = {}
        self._last_energy_time: float | None = None
        self._energy_input_kwh: float = 0.0
        self._energy_output_kwh: float = 0.0
        self._last_response_time: float | None = None
        self._rx_buffer = bytearray()
        self._rx_header = bytearray()
        self._rx_expected_len = 0
        self._response_event = asyncio.Event()
        self._response_data: dict | None = None
        self.api = None

    @property
    def device_name(self) -> str:
        return self.device.get("name", "Fossibot")

    @property
    def device_mac(self) -> str:
        return self.device.get("device_id", self._ble_address)

    @property
    def device_model(self) -> str:
        return self.device.get("productInfo", {}).get("name", "Power Station")

    @property
    def sw_version(self) -> str | None:
        ac = self._data.get("acVersion")
        ac_sub = self._data.get("acVersionSub")
        if ac is not None:
            ver = str(ac)
            if ac_sub is not None:
                ver += f".{ac_sub}"
            return ver
        return None

    @property
    def hw_version(self) -> str | None:
        panel = self._data.get("panelVersion")
        if panel is not None:
            return str(panel)
        return None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def device_available(self) -> bool:
        if not self._connected:
            return False
        if self._last_response_time is None:
            return False
        return (time.monotonic() - self._last_response_time) < self._poll_interval * 3

    def _reset_rx_state(self):
        self._rx_buffer = bytearray()
        self._rx_header = bytearray()
        self._rx_expected_len = 0

    def _notification_handler(self, sender, data: bytearray):
        arr = bytearray(data)

        if len(self._rx_buffer) == 0 and len(self._rx_header) == 0:
            if len(arr) < 2:
                return
            func_code = arr[1] if arr[1] <= 128 else arr[1] - 128

            if func_code in (3, 4):
                if len(arr) < 6:
                    self._rx_header = arr
                    return
                self._rx_header = arr[:6]
                self._rx_buffer = arr[6:]
                self._rx_expected_len = 2 * ((arr[4] << 8) | arr[5]) + 2
            elif func_code in (5, 6):
                self._reset_rx_state()
                return
            else:
                return
        else:
            self._rx_buffer.extend(arr)

        if len(self._rx_buffer) >= self._rx_expected_len:
            full_packet = bytes(self._rx_header) + bytes(self._rx_buffer)
            self._reset_rx_state()
            parsed = parse_response(full_packet)
            if parsed:
                self._response_data = parsed
                self.hass.loop.call_soon_threadsafe(self._response_event.set)
                self._process_parsed(parsed)

    async def _send_command(self, data: bytes, timeout: float = 5.0) -> dict | None:
        if not self._ble_client or not self._ble_client.is_connected:
            return None

        self._reset_rx_state()
        self._response_event.clear()
        self._response_data = None

        await self._ble_client.write_gatt_char(BLE_WRITE_UUID, data, response=True)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            return self._response_data
        except asyncio.TimeoutError:
            _LOGGER.debug("BLE response timeout")
            return None

    async def async_connect(self):
        address = self._ble_address

        if not any(c in address for c in (":", "-")) or len(address) < 12:
            _LOGGER.info("Scanning for BLE device: %s", address)
            devices = await BleakScanner.discover(timeout=10.0)
            found = None
            for d in devices:
                if d.name and (d.name == address or d.address == address):
                    found = d
                    break
                if d.name and any(d.name.startswith(p) for p in BLE_DEVICE_PREFIXES):
                    found = d
            if not found:
                raise ConnectionError(f"BLE device not found: {address}")
            address = found.address
            _LOGGER.info("Found BLE device: %s (%s)", found.name, found.address)

        def disconnected_callback(client):
            self._connected = False
            if not self._intentional_disconnect:
                _LOGGER.warning("BLE disconnected, scheduling reconnect")
                asyncio.run_coroutine_threadsafe(
                    self._reconnect_loop(), self.hass.loop
                )

        self._ble_client = BleakClient(address, disconnected_callback=disconnected_callback)
        await self._ble_client.connect()

        await self._ble_client.start_notify(BLE_NOTIFY_UUID, self._notification_handler)

        self._connected = True
        _LOGGER.info("BLE connected to %s", address)
        self._schedule_poll()

    async def _reconnect_loop(self):
        delay = 5
        max_delay = 300
        while not self._connected and not self._intentional_disconnect:
            _LOGGER.info("Attempting BLE reconnect in %s seconds", delay)
            await asyncio.sleep(delay)
            if self._intentional_disconnect:
                return
            try:
                if self._ble_client:
                    try:
                        await self._ble_client.disconnect()
                    except Exception:
                        pass
                    self._ble_client = None
                await self.async_connect()
                _LOGGER.info("BLE reconnected successfully")
                return
            except Exception as e:
                _LOGGER.warning("BLE reconnect failed: %s", e)
                delay = min(delay * 2, max_delay)

    def _process_parsed(self, parsed: dict):
        try:
            self._process_parsed_inner(parsed)
        except Exception:
            _LOGGER.exception("Error processing parsed Modbus data (fc=%s)", parsed.get("func_code"))

    def _process_parsed_inner(self, parsed: dict):
        named = parsed["named"]
        fc = parsed["func_code"]
        self._last_response_time = time.monotonic()

        if fc == 4:
            for key in ("battery_soc", "battery_voltage", "ambient_temp",
                        "total_input_power", "totalOutputPower", "pv_energy_today",
                        "dcChargePower", "acChargePower", "pv1ChargePower",
                        "pv2ChargePower", "pv3ChargePower", "pv4ChargePower",
                        "acGridPower", "remainChargeTimeMin",
                        "acVersion", "acVersionSub", "panelVersion"):
                if key in named:
                    self._data[key] = named[key]

            pv_total_h = named.get("pvChargeEnergyTotalH", 0)
            pv_total_l = named.get("pvChargeEnergyTotalL", 0)
            if "pvChargeEnergyTotalH" in named:
                total_raw = (pv_total_h << 16) | pv_total_l
                self._data["pv_energy_total"] = round(total_raw * 10 / 1000, 2)

            now = time.monotonic()
            if self._last_energy_time is not None:
                dt_h = (now - self._last_energy_time) / 3600
                input_w = self._data.get("total_input_power", 0)
                output_w = self._data.get("totalOutputPower", 0)
                self._energy_input_kwh += (input_w / 1000) * dt_h
                self._energy_output_kwh += (output_w / 1000) * dt_h
                self._data["energy_input_kwh"] = round(self._energy_input_kwh, 4)
                self._data["energy_output_kwh"] = round(self._energy_output_kwh, 4)
            self._last_energy_time = now

            if "ledState" in named:
                self._data["led_mode"] = named["ledState"]

            soc = self._data.get("battery_soc")
            output_w = self._data.get("totalOutputPower", 0)
            if soc is not None and output_w > 0:
                total_drain = output_w * 1.5 + 22
                self._data["remain_discharge_hours"] = round(
                    (CAPACITY_WH * soc / 100) / total_drain, 1
                )

            rc_min = named.get("remainChargeTimeMin", 0)
            if rc_min and rc_min > 0:
                self._data["remain_charge_minutes"] = rc_min

        if fc == 3:
            if "usbOutputCmd" in named:
                self._data["usb_on"] = named["usbOutputCmd"] > 0
                self._data["usbOutputCmd"] = named["usbOutputCmd"]
            if "dcOutputCmd" in named:
                self._data["dc_on"] = named["dcOutputCmd"] > 0
                self._data["dcOutputCmd"] = named["dcOutputCmd"]
            if "acOutputCmd" in named:
                self._data["ac_on"] = named["acOutputCmd"] > 0
                self._data["acOutputCmd"] = named["acOutputCmd"]
            if "ledCmd" in named:
                self._data["led_mode"] = named["ledCmd"]
            if "keySound" in named:
                self._data["key_sound"] = named["keySound"] > 0
            if "silentCharging" in named:
                self._data["silent_charging"] = named["silentCharging"] > 0
            if "low_batt_notify_enabled" in named:
                self._data["low_batt_notify_enabled"] = named["low_batt_notify_enabled"]
            if "low_batt_notify_threshold" in named:
                self._data["low_batt_notify_threshold"] = named["low_batt_notify_threshold"]
            for key in ("usbStandbyTime", "acStandbyTime", "dcStandbyTime",
                        "screenRestTime", "machineUnusedTime",
                        "dischargeLimitx10", "chargeLimitx10"):
                if key in named:
                    self._data[key] = named[key]

        self.hass.loop.call_soon_threadsafe(self._fire_update)

    @callback
    def _fire_update(self):
        self.async_set_updated_data(dict(self._data))

    def _schedule_poll(self):
        if self._poll_task and not self._poll_task.done():
            return
        self._poll_task = self.hass.async_create_task(self._poll_loop())

    async def _poll_loop(self):
        while self._connected:
            await self._async_poll_once()
            await asyncio.sleep(self._poll_interval)

    async def _async_poll_once(self):
        if not self._ble_client or not self._connected:
            return
        try:
            fc4 = build_read_request(self._modbus_addr, 4, 0, self._modbus_count)
            await self._send_command(fc4)
            await asyncio.sleep(0.5)

            fc3_count = max(self._modbus_count, 86)
            fc3 = build_read_request(self._modbus_addr, 3, 0, fc3_count)
            await self._send_command(fc3)
        except Exception:
            _LOGGER.exception("Error during BLE poll")

    async def async_write_register(self, register: int, value: int):
        if not self._ble_client or not self._connected:
            _LOGGER.warning("Cannot write register %d: BLE not connected", register)
            return
        try:
            cmd = build_write_request(self._modbus_addr, register, value)
            await self._ble_client.write_gatt_char(BLE_WRITE_UUID, cmd, response=True)
            _LOGGER.debug("BLE wrote register %d = %d", register, value)
            await asyncio.sleep(0.5)
            await self._async_poll_once()
        except Exception:
            _LOGGER.exception("Error writing register %d via BLE", register)

    async def async_disconnect(self):
        self._intentional_disconnect = True
        self._connected = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        try:
            if self._ble_client and self._ble_client.is_connected:
                await self._ble_client.stop_notify(BLE_NOTIFY_UUID)
                await self._ble_client.disconnect()
        except Exception:
            _LOGGER.debug("Error during BLE disconnect", exc_info=True)
        finally:
            self._ble_client = None

    async def _async_update_data(self):
        return dict(self._data)
