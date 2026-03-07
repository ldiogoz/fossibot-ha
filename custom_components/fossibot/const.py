DOMAIN = "fossibot"
PLATFORMS = ["sensor", "switch", "number", "select", "button"]

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

SPACE_ID = "mp-6c382a98-49b8-40ba-b761-645d83e8ee74"
CLIENT_SECRET = "5rCEdl/nx7IgViBe4QYRiQ=="
API_URL = "https://api.next.bspapp.com/client"
MQTT_BROKER = "mqtt.sydpower.com"
MQTT_PORT = 8083
MQTT_PASSWORD = "client123"

BLE_SERVICE_UUID = "0000a002-0000-1000-8000-00805f9b34fb"
BLE_WRITE_UUID = "0000c304-0000-1000-8000-00805f9b34fb"
BLE_NOTIFY_UUID = "0000c305-0000-1000-8000-00805f9b34fb"

CLIENT_INFO = {
    "PLATFORM": "app",
    "OS": "android",
    "APPID": "__UNI__55F5E7F",
    "DEVICEID": "621DF9EDD14684453E5099DCF6B8D26B",
    "channel": "google",
    "scene": 1001,
    "uniPlatform": "app",
    "browserName": "chrome",
    "deviceBrand": "google",
    "appId": "__UNI__55F5E7F",
    "appWgtVersion": "1.5.9",
    "osVersion": "16",
    "romName": "Android",
    "deviceModel": "sdk_gphone64_arm64",
    "browserVersion": "145.0.7632.120",
    "deviceType": "phone",
    "deviceId": "621DF9EDD14684453E5099DCF6B8D26B",
    "ua": "Mozilla/5.0 (Linux; Android 16; sdk_gphone64_arm64 Build/BE2A.250530.026.D1; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/145.0.7632.120 Mobile Safari/537.36 Html5Plus/1.0 (Immersed/52.190475)",
    "appName": "BrightEMS",
    "uniRuntimeVersion": "5.01",
    "romVersion": "16",
    "appVersion": "1.5.9",
    "osName": "android",
    "appVersionCode": 159,
    "appLanguage": "en",
    "uniCompilerVersion": "5.01",
    "locale": "en",
    "LOCALE": "en",
}

INPUT_REGISTER_MAP = {
    0: "dcChargePower", 2: "acChargePower", 3: "pv1ChargePower",
    4: "pv2ChargePower", 5: "pv3ChargePower", 6: "pv4ChargePower",
    7: "acGridPower", 12: "acOutputPower",
    18: "outputStatusMask", 19: "batteryVoltage",
    20: "totalOutputPower", 21: "chargingFlag",
    25: "usbOutputState", 26: "dcOutputState", 27: "acOutputState", 28: "ledState",
    31: "mainBatteryRaw", 32: "slave1BatteryRaw", 33: "slave2BatteryRaw",
    34: "slave3BatteryRaw", 35: "slave4BatteryRaw",
    47: "acVersion", 48: "acVersionSub", 50: "panelVersion",
    52: "ambientTemp",
    56: "batterySOCx10",
    58: "remainChargeTimeMin",
    59: "pvChargeEnergyTotalH", 60: "pvChargeEnergyTotalL",
    61: "pvChargeEnergyToday",
    71: "remainChargeTime", 72: "remainDischargeTime",
}

HOLDING_REGISTER_MAP = {
    15: "dcInputType",
    24: "usbOutputCmd", 25: "dcOutputCmd", 26: "acOutputCmd", 27: "ledCmd",
    56: "keySound", 57: "silentCharging",
    59: "usbStandbyTime", 60: "acStandbyTime", 61: "dcStandbyTime",
    62: "screenRestTime", 64: "remoteShutdown",
    66: "dischargeLimitx10", 67: "chargeLimitx10",
    68: "machineUnusedTime",
    84: "lowBatteryNotification",
}

POLL_INTERVAL = 5
POLL_INTERVAL_MIN = 3
POLL_INTERVAL_MAX = 60
CAPACITY_WH = 2048
CONF_POLL_INTERVAL = "poll_interval"
CONF_ENABLE_ENERGY_SENSORS = "enable_energy_sensors"
CONF_ENABLE_ADVANCED_CONTROLS = "enable_advanced_controls"
CONF_CONNECTION_TYPE = "connection_type"
CONF_BLE_ADDRESS = "ble_address"
CONNECTION_TYPE_MQTT = "mqtt"
CONNECTION_TYPE_BLE = "ble"
