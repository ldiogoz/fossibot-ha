import logging
import struct

from .const import INPUT_REGISTER_MAP, HOLDING_REGISTER_MAP

_LOGGER = logging.getLogger(__name__)


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_read_request(slave_addr: int, func_code: int, start_reg: int, reg_count: int) -> bytes:
    buf = struct.pack(">BBHH", slave_addr, func_code, start_reg, reg_count)
    crc = crc16_modbus(buf)
    return buf + struct.pack(">H", crc)


def build_write_request(slave_addr: int, reg_addr: int, value: int) -> bytes:
    buf = struct.pack(">BBHH", slave_addr, 0x06, reg_addr, value)
    crc = crc16_modbus(buf)
    return buf + struct.pack(">H", crc)


def parse_response(data: bytes) -> dict | None:
    if len(data) < 7:
        _LOGGER.debug("Modbus response too short: %d bytes", len(data))
        return None

    slave_addr = data[0]
    func_code = data[1] if data[1] <= 128 else data[1] - 128
    if func_code not in (3, 4):
        _LOGGER.debug("Unexpected Modbus function code: %d", data[1])
        return None

    start_reg = (data[2] << 8) | data[3]
    reg_count = (data[4] << 8) | data[5]
    expected_len = reg_count * 2 + 6 + 2
    if len(data) < expected_len:
        _LOGGER.debug("Modbus response truncated: got %d, expected %d (fc=%d, regs=%d)",
                      len(data), expected_len, func_code, reg_count)
        return None

    crc_data = data[: len(data) - 2]
    crc_received = (data[-2] << 8) | data[-1]
    if crc16_modbus(crc_data) != crc_received:
        _LOGGER.debug("Modbus CRC mismatch (fc=%d)", func_code)
        return None

    registers = []
    for i in range(reg_count):
        offset = 6 + i * 2
        registers.append((data[offset] << 8) | data[offset + 1])

    reg_map = HOLDING_REGISTER_MAP if func_code == 3 else INPUT_REGISTER_MAP
    named: dict = {}
    for i in range(reg_count):
        name = reg_map.get(start_reg + i)
        if name:
            named[name] = registers[i]

    if func_code == 4:
        if "batterySOCx10" in named:
            named["battery_soc"] = named["batterySOCx10"] / 10
        if "batteryVoltage" in named:
            named["battery_voltage"] = named["batteryVoltage"] / 10
        if "ambientTemp" in named:
            named["ambient_temp"] = named["ambientTemp"] / 10
        if "pvChargeEnergyToday" in named:
            named["pv_energy_today"] = round(named["pvChargeEnergyToday"] * 10 / 1000, 2)
        pv = max(named.get("pv1ChargePower", 0), named.get("pv2ChargePower", 0),
                 named.get("pv3ChargePower", 0), named.get("pv4ChargePower", 0))
        total_in = named.get("dcChargePower", 0) + named.get("acChargePower", 0) + pv + named.get("acGridPower", 0)
        named["total_input_power"] = total_in if total_in >= 5 else 0

    if func_code == 3:
        if "lowBatteryNotification" in named:
            raw = named["lowBatteryNotification"]
            named["low_batt_notify_enabled"] = bool((raw >> 8) & 1)
            named["low_batt_notify_threshold"] = raw & 0xFF

    return {
        "slave_addr": slave_addr,
        "func_code": func_code,
        "start_reg": start_reg,
        "reg_count": reg_count,
        "registers": registers,
        "named": named,
    }


def is_write_confirm(data: bytes) -> bool:
    return len(data) == 8 and data[1] == 0x06
