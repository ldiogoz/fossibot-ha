# Fossibot Power Station - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for **Fossibot** portable power stations (F2400-B and compatible models) via the BSApp / BrightEMS cloud API and **Bluetooth Low Energy (BLE)**.

## Features

- **14 Sensors** — Battery %, input/output power, solar power, voltage, temperature, charge/discharge time, energy tracking
- **6 Switches** — AC/DC/USB output, key sound, silent charging, low battery notification
- **3 Number Controls** — Discharge limit, charge limit, low battery threshold
- **6 Select Controls** — AC/DC/USB standby time, machine auto-off, screen rest, LED mode
- **2 Buttons** — Remote shutdown, refresh data
- **Diagnostics** — Download full device state snapshot from Settings for troubleshooting
- **Energy Dashboard Ready** — Solar production, charge/discharge energy with proper `TOTAL_INCREASING` state class
- **Real-time Updates** — MQTT push via cloud broker with configurable polling interval
- **Bluetooth (BLE) Support** — Connect directly via Bluetooth as an alternative to cloud MQTT
- **Auto Token Refresh** — Handles expired sessions transparently
- **Device Availability** — Entities go unavailable when the power station is turned off or unreachable
- **MQTT Reconnect** — Exponential backoff reconnection (5s → 5min) on connection loss
- **Multi-device Support** — All power stations on your account are discovered automatically
- **Configurable Options** — Poll interval, energy sensor toggle, advanced controls toggle, connection type (MQTT/BLE)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the **⋮** menu → **Custom repositories**
3. Add this repository URL with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/fossibot` folder to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings** → **Devices & Services** → **+ Add Integration**
2. Search for **Fossibot**
3. Enter your BSApp / BrightEMS account credentials
4. The integration will discover your devices and create all entities

## Configuration Options

After setup, click **Configure** on the integration to adjust:

| Option | Default | Description |
|--------|---------|-------------|
| Connection Type | MQTT | Choose between MQTT (Cloud) or Bluetooth (BLE) |
| BLE Device Address | — | Bluetooth address or device name (required for BLE mode) |
| Poll Interval | 5s | How often to request data (3–60 seconds) |
| Enable Energy Sensors | On | Show energy tracking sensors for the HA Energy Dashboard |
| Enable Advanced Controls | On | Show standby times, limits, key sound, silent charging, etc. |

Changes take effect immediately (the integration reloads automatically).

## Bluetooth (BLE) Connection

As an alternative to the cloud MQTT connection, you can connect directly to your power station via Bluetooth Low Energy (BLE). This provides local-only communication without requiring internet access after the initial setup.

### Requirements
- Bluetooth adapter on the Home Assistant host (built-in or USB dongle)
- Power station within Bluetooth range (~10m)
- BSApp account still required for initial device discovery

### Setup
1. Install the integration normally with your BSApp credentials
2. Go to the integration's **Configure** options
3. Set **Connection Type** to **Bluetooth (BLE)**
4. Enter the **BLE Device Address** — this can be:
   - The Bluetooth MAC address (e.g., `E8:06:90:C6:F7:AE`)
   - The device's Bluetooth name (e.g., `POWER-XXXX`)
5. Save — the integration will reconnect via BLE

### Web Panel BLE
The included web panel also supports direct BLE connections from your browser:
- Click **🔵 Connect via BLE** in the sidebar to scan and connect
- Or use **🔵 Offline Mode (BLE Only)** on the login screen to skip authentication entirely
- Requires Chrome or Edge browser (Web Bluetooth API)
- Works on localhost without HTTPS

## Energy Dashboard

The integration provides sensors compatible with the HA Energy Dashboard:

| Sensor | Dashboard Section | Description |
|--------|------------------|-------------|
| Solar Energy Today | Solar Panels | Daily PV production (resets daily) |
| Solar Energy Total | Solar Panels | Lifetime PV production |
| Energy Charged | Battery Storage | Cumulative energy input |
| Energy Consumed | Home Consumption | Cumulative energy output |

Go to **Settings** → **Dashboards** → **Energy** to configure.

## Device Availability

When your power station is turned off or goes out of range, all entities automatically switch to **unavailable** in Home Assistant. This prevents stale values from appearing on dashboards.

Availability is determined by MQTT response timing — if no data is received within 3× the poll interval, the device is marked unavailable. Entities return to normal as soon as the power station responds again.

## Diagnostics

For troubleshooting, you can download a diagnostics snapshot:

1. Go to **Settings** → **Devices & Services**
2. Click on the **Fossibot** integration
3. Click the **⋮** menu → **Download diagnostics**

The snapshot includes: connection status, poll interval, firmware versions, data keys, and current sensor values (no credentials are included).

## Entities

### Sensors
| Entity | Unit | Description |
|--------|------|-------------|
| Battery | % | State of charge |
| Input Power | W | Total charging power |
| Output Power | W | Total discharge power |
| Solar Power | W | PV panel power |
| DC Charge Power | W | DC input power |
| AC Charge Power | W | AC input power |
| Solar Energy Today | kWh | Daily solar production |
| Solar Energy Total | kWh | Lifetime solar production |
| Energy Charged | kWh | Cumulative input energy |
| Energy Consumed | kWh | Cumulative output energy |
| Battery Voltage | V | Battery voltage |
| Temperature | °C | Ambient temperature |
| Charge Time Remaining | min | Estimated charge time |
| Discharge Time Remaining | h | Estimated runtime |

### Switches
| Entity | Description |
|--------|-------------|
| AC Output | Toggle AC inverter |
| DC Output | Toggle DC output |
| USB Output | Toggle USB ports |
| Key Sound | Toggle button beep |
| Silent Charging | Toggle fan reduction |
| Low Battery Notification | Toggle low battery alert |

### Number Controls
| Entity | Range | Description |
|--------|-------|-------------|
| Discharge Limit | 0-50% | Minimum battery level |
| Charge Limit | 60-100% | Maximum charge level |
| Low Battery Threshold | 5-50% | Alert threshold |

### Select Controls
| Entity | Description |
|--------|-------------|
| AC Standby Time | Auto-off when no AC load |
| DC Standby Time | Auto-off when no DC load |
| USB Standby Time | Auto-off when no USB load |
| Machine Unused Auto-Off | Auto-off when idle |
| Screen Rest Time | Display sleep timer |
| LED Mode | Off / On / SOS / Flash |

### Buttons
| Entity | Description |
|--------|-------------|
| Remote Shutdown | Power off the device |
| Refresh Data | Force data poll |

## Troubleshooting

### Integration won't load / "Config entry not ready"
The integration raises `ConfigEntryNotReady` if the API or MQTT connection fails during setup. Home Assistant will automatically retry. Check your internet connection and BSApp credentials.

### Entities show "unavailable"
This means the power station isn't responding. Possible causes:
- Power station is turned off
- Power station is out of WiFi/cellular range
- Cloud API is temporarily down

Entities will recover automatically once the device starts responding again.

### Enable debug logging
Add to your `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.fossibot: debug
```
This enables detailed logs for API requests, MQTT messages, Modbus parsing, and register writes.

## Tested Devices

- Fossibot F2400-B

Other Fossibot models using the BSApp / BrightEMS app should also work but are untested.

## Requirements

- Home Assistant 2024.1.0+
- BSApp / BrightEMS account
- **MQTT mode**: Internet connection (cloud API + MQTT)
- **BLE mode**: Bluetooth adapter on the HA host, device within range

## License

MIT
