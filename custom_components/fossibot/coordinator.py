import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as paho_mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import FossibotApi
from .const import DOMAIN, MQTT_BROKER, MQTT_PORT, MQTT_PASSWORD, POLL_INTERVAL, CAPACITY_WH
from .modbus import build_read_request, build_write_request, parse_response, is_write_confirm

_LOGGER = logging.getLogger(__name__)


class FossibotCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: FossibotApi, device: dict, poll_interval: int = POLL_INTERVAL):
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=None,
        )
        self.api = api
        self.device = device
        self._mqtt_client: paho_mqtt.Client | None = None
        self._device_id_clean = device.get("device_id", "").replace(":", "")
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

    @property
    def device_name(self) -> str:
        return self.device.get("name", "Fossibot")

    @property
    def device_mac(self) -> str:
        return self.device.get("device_id", "unknown")

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

    async def async_connect(self):
        mqtt_creds = await self.api.get_mqtt_credentials(self.device.get("device_id", ""))
        host = mqtt_creds.get("mqtt_host", MQTT_BROKER)
        mqtt_username = mqtt_creds.get("access_token", "")
        user_id = self.api.user_id or ""

        ts = int(time.time() * 1000)
        d = ts % 10
        api_secret = user_id[d:]
        sign_hash = hashlib.md5(f"timestamp={ts}&api_secret={api_secret}".encode()).hexdigest()
        client_id = f"client_{user_id}_{sign_hash}_{ts}"

        self._mqtt_client = paho_mqtt.Client(
            client_id=client_id,
            transport="websockets",
            protocol=paho_mqtt.MQTTv311,
        )
        self._mqtt_client.username_pw_set(mqtt_username, MQTT_PASSWORD)
        self._mqtt_client.ws_set_options(path="/mqtt")
        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_message = self._on_message
        self._mqtt_client.on_disconnect = self._on_disconnect

        await self.hass.async_add_executor_job(
            self._mqtt_client.connect, host, MQTT_PORT, 60
        )
        self._mqtt_client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            _LOGGER.error("MQTT connect failed with code %s", rc)
            return
        self._connected = True
        _LOGGER.info("MQTT connected to Fossibot device %s", self._device_id_clean)
        did = self._device_id_clean
        client.subscribe([
            (f"{did}/device/response/state", 0),
            (f"{did}/device/response/faultCode", 0),
            (f"{did}/device/response/client/+", 0),
            (f"{did}/device/webhook", 0),
        ])
        self._schedule_poll()

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if self._intentional_disconnect:
            _LOGGER.info("MQTT disconnected intentionally")
            return
        _LOGGER.warning("MQTT disconnected (rc=%s), scheduling reconnect", rc)
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.run_coroutine_threadsafe(
            self._reconnect_loop(), self.hass.loop
        )

    async def _reconnect_loop(self):
        delay = 5
        max_delay = 300
        while not self._connected and not self._intentional_disconnect:
            _LOGGER.info("Attempting MQTT reconnect in %s seconds", delay)
            await asyncio.sleep(delay)
            if self._intentional_disconnect:
                return
            try:
                if self._mqtt_client:
                    self._mqtt_client.loop_stop()
                    self._mqtt_client.disconnect()
                    self._mqtt_client = None
                await self.async_connect()
                _LOGGER.info("MQTT reconnected successfully")
                return
            except Exception as e:
                _LOGGER.warning("MQTT reconnect failed: %s", e)
                delay = min(delay * 2, max_delay)

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload

            if "/device/response/client" in topic:
                data_bytes = bytes(payload)
                if is_write_confirm(data_bytes):
                    asyncio.run_coroutine_threadsafe(self._async_poll_once(), self.hass.loop)
                    return
                parsed = parse_response(data_bytes)
                if parsed:
                    self._process_parsed(parsed)
                else:
                    _LOGGER.debug("Unparseable MQTT payload (%d bytes) on %s", len(data_bytes), topic)
        except Exception:
            _LOGGER.exception("Error processing MQTT message on %s", msg.topic)

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
        self._poll_task = asyncio.run_coroutine_threadsafe(
            self._poll_loop(), self.hass.loop
        )

    async def _poll_loop(self):
        while self._connected:
            await self._async_poll_once()
            await asyncio.sleep(self._poll_interval)

    async def _async_poll_once(self):
        if not self._mqtt_client or not self._connected:
            return
        try:
            topic = f"{self._device_id_clean}/client/request/data"
            fc4 = build_read_request(self._modbus_addr, 4, 0, self._modbus_count)
            await self.hass.async_add_executor_job(
                self._mqtt_client.publish, topic, fc4, 0, False
            )
            await asyncio.sleep(0.5)
            fc3_count = max(self._modbus_count, 86)
            fc3 = build_read_request(self._modbus_addr, 3, 0, fc3_count)
            await self.hass.async_add_executor_job(
                self._mqtt_client.publish, topic, fc3, 0, False
            )
        except Exception:
            _LOGGER.exception("Error during MQTT poll")

    async def async_write_register(self, register: int, value: int):
        if not self._mqtt_client or not self._connected:
            _LOGGER.warning("Cannot write register %d: MQTT not connected", register)
            return
        try:
            topic = f"{self._device_id_clean}/client/request/data"
            cmd = build_write_request(self._modbus_addr, register, value)
            await self.hass.async_add_executor_job(
                self._mqtt_client.publish, topic, cmd, 0, False
            )
            _LOGGER.debug("Wrote register %d = %d", register, value)
            await asyncio.sleep(0.5)
            await self._async_poll_once()
        except Exception:
            _LOGGER.exception("Error writing register %d", register)

    async def async_disconnect(self):
        self._intentional_disconnect = True
        self._connected = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        try:
            if self._mqtt_client:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
        except Exception:
            _LOGGER.debug("Error during MQTT disconnect", exc_info=True)
        finally:
            self._mqtt_client = None
            self._mqtt_client = None

    async def _async_update_data(self):
        return dict(self._data)
