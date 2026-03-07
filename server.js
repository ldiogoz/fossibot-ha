const express = require("express");
const axios = require("axios");
const path = require("path");
const crypto = require("crypto");
const mqtt = require("mqtt");
const fs = require("fs");

const app = express();
const PORT = 3000;
const CREDS_FILE = path.join(__dirname, ".credentials.json");

const SPACE_ID = "mp-6c382a98-49b8-40ba-b761-645d83e8ee74";
const CLIENT_SECRET = "5rCEdl/nx7IgViBe4QYRiQ==";
const API_URL = "https://api.next.bspapp.com/client";

const CLIENT_INFO = {
  PLATFORM: "app",
  OS: "android",
  APPID: "__UNI__55F5E7F",
  DEVICEID: "621DF9EDD14684453E5099DCF6B8D26B",
  channel: "google",
  scene: 1001,
  uniPlatform: "app",
  browserName: "chrome",
  deviceBrand: "google",
  appId: "__UNI__55F5E7F",
  appWgtVersion: "1.5.9",
  osVersion: "16",
  romName: "Android",
  deviceModel: "sdk_gphone64_arm64",
  browserVersion: "145.0.7632.120",
  deviceType: "phone",
  deviceId: "621DF9EDD14684453E5099DCF6B8D26B",
  ua: "Mozilla/5.0 (Linux; Android 16; sdk_gphone64_arm64 Build/BE2A.250530.026.D1; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/145.0.7632.120 Mobile Safari/537.36 Html5Plus/1.0 (Immersed/52.190475)",
  appName: "BrightEMS",
  uniRuntimeVersion: "5.01",
  romVersion: "16",
  appVersion: "1.5.9",
  osName: "android",
  appVersionCode: 159,
  appLanguage: "en",
  uniCompilerVersion: "5.01",
  locale: "en",
  LOCALE: "en",
};

const REQUEST_HEADERS = {
  "Content-Type": "application/json",
  "Connection": "Keep-Alive",
  "Accept-Encoding": "gzip",
  "User-Agent": "Mozilla/5.0 (Linux; Android 16; sdk_gphone64_arm64 Build/BE2A.250530.026.D1; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/145.0.7632.120 Mobile Safari/537.36 (Immersed/52.190475) Html5Plus/1.0",
};

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

let accessToken = null;
let uniIdToken = null;
let userInfo = null;
let savedCredentials = null;

function loadCredentials() {
  try {
    if (fs.existsSync(CREDS_FILE)) {
      savedCredentials = JSON.parse(fs.readFileSync(CREDS_FILE, "utf8"));
      return savedCredentials;
    }
  } catch (e) {}
  return null;
}

function saveCredentials(username, password) {
  savedCredentials = { username, password };
  fs.writeFileSync(CREDS_FILE, JSON.stringify(savedCredentials), "utf8");
}

async function autoLogin() {
  const creds = loadCredentials();
  if (!creds) return;
  try {
    const data = await invokeFunction("user/pub/login", creds);
    if (data.data?.token) {
      uniIdToken = data.data.token;
      userInfo = data.data;
      console.log("Auto-login successful for", creds.username);
    }
  } catch (e) {
    console.log("Auto-login failed:", e.message);
  }
}

function generateSignature(data) {
  let signString = "";
  Object.keys(data).sort().forEach((key) => {
    if (data[key]) {
      signString = signString + "&" + key + "=" + data[key];
    }
  });
  signString = signString.slice(1);
  return crypto.createHmac("md5", CLIENT_SECRET).update(signString).digest("hex");
}

async function apiRequest(method, params, token) {
  const timestamp = Date.now();

  const data = { method, params, spaceId: SPACE_ID, timestamp };
  const headers = { ...REQUEST_HEADERS };

  if (token) {
    data.token = token;
    headers["x-basement-token"] = token;
  }

  headers["x-serverless-sign"] = generateSignature(data);

  const response = await axios.post(API_URL, data, { headers });

  return response.data;
}

async function anonymousAuth() {
  const result = await apiRequest(
    "serverless.auth.user.anonymousAuthorize",
    "{}",
    null
  );
  if (result.data && result.data.accessToken) {
    return result.data.accessToken;
  }
  throw new Error("Anonymous auth failed: " + JSON.stringify(result));
}

async function ensureAccessToken() {
  if (!accessToken) {
    accessToken = await anonymousAuth();
  }
  return accessToken;
}

async function invokeFunction(url, data = {}, _isRetry = false) {
  const token = await ensureAccessToken();
  const params = JSON.stringify({
    functionTarget: "router",
    functionArgs: {
      $url: url,
      data: { locale: "en", ...data },
      clientInfo: CLIENT_INFO,
      ...(uniIdToken ? { uniIdToken } : {}),
    },
  });

  try {
    const result = await apiRequest("serverless.function.runtime.invoke", params, token);
    if (!_isRetry && result.data?.errCode && /token.*expired|TOKEN_EXPIRED|uni-id-token-expired/i.test(result.data.errCode + " " + (result.data.errMsg || ""))) {
      const refreshed = await tryAutoRelogin();
      if (refreshed) return invokeFunction(url, data, true);
    }
    return result;
  } catch (err) {
    if (err.response?.data?.error?.code === "GATEWAY_INVALID_TOKEN") {
      accessToken = await anonymousAuth();
      const result = await apiRequest("serverless.function.runtime.invoke", params, accessToken);
      if (!_isRetry && result.data?.errCode && /token.*expired|TOKEN_EXPIRED|uni-id-token-expired/i.test(result.data.errCode + " " + (result.data.errMsg || ""))) {
        const refreshed = await tryAutoRelogin();
        if (refreshed) return invokeFunction(url, data, true);
      }
      return result;
    }
    throw err;
  }
}

let reloginInProgress = null;
async function tryAutoRelogin() {
  if (reloginInProgress) return reloginInProgress;
  reloginInProgress = (async () => {
    if (!savedCredentials) loadCredentials();
    if (!savedCredentials) return false;
    try {
      uniIdToken = null;
      accessToken = await anonymousAuth();
      const data = await invokeFunction("user/pub/login", savedCredentials, true);
      if (data.data?.token) {
        uniIdToken = data.data.token;
        userInfo = data.data;
        console.log("Auto-relogin successful");
        return true;
      }
    } catch (e) {
      console.log("Auto-relogin failed:", e.message);
    }
    return false;
  })();
  try { return await reloginInProgress; }
  finally { reloginInProgress = null; }
}

app.post("/api/login", async (req, res) => {
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ success: false, error: "Username and password are required" });
  }

  try {
    const data = await invokeFunction("user/pub/login", { username, password });

    if (data.data && data.data.token) {
      uniIdToken = data.data.token;
      userInfo = data.data;
      saveCredentials(username, password);
      return res.json({ success: true, data: data.data });
    }

    if (data.data && data.data.errCode) {
      return res.json({ success: false, error: data.data.errMsg || "Login failed", data: data.data });
    }

    return res.json({ success: false, error: "Unexpected response", data });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message, details: err.response?.data });
  }
});

app.get("/api/devices", async (req, res) => {
  if (!uniIdToken) {
    return res.status(401).json({ success: false, error: "Not authenticated" });
  }

  try {
    const data = await invokeFunction("client/device/kh/getList_v2", {
      pageIndex: 1,
      pageSize: 10,
      isForce: true,
    });

    if (data.data && data.data.rows) {
      return res.json({ success: true, devices: data.data.rows, total: data.data.total });
    }

    if (data.data?.errCode) {
      console.log("Device list error:", data.data.errCode, data.data.errMsg);
      return res.json({ success: false, error: data.data.errMsg || data.data.errCode, needsLogin: true });
    }

    console.log("Unexpected device list response:", JSON.stringify(data).substring(0, 500));
    return res.json({ success: false, error: "Unexpected response", data });
  } catch (err) {
    return res.status(500).json({ success: false, error: err.message, details: err.response?.data });
  }
});

app.get("/api/status", (req, res) => {
  res.json({ authenticated: !!uniIdToken, user: userInfo });
});

app.post("/api/logout", (req, res) => {
  disconnectAllMqtt();
  accessToken = null;
  uniIdToken = null;
  userInfo = null;
  res.json({ success: true });
});

const INPUT_REGISTER_MAP = {
  0: "dcChargePower", 2: "acChargePower", 3: "pv1ChargePower",
  4: "pv2ChargePower", 5: "pv3ChargePower", 6: "pv4ChargePower",
  7: "acGridPower", 12: "acOutputPower",
  18: "outputStatusMask", 19: "batteryVoltage",
  20: "totalOutputPower", 21: "chargingFlag",
  25: "usbOutputState", 26: "dcOutputState", 27: "acOutputState", 28: "ledState",
  31: "mainBatteryRaw", 32: "slave1BatteryRaw", 33: "slave2BatteryRaw",
  34: "slave3BatteryRaw", 35: "slave4BatteryRaw",
  37: "mainBmsStatus", 39: "slave1BmsStatus",
  41: "slave2BmsStatus", 43: "slave3BmsStatus", 45: "slave4BmsStatus",
  47: "acVersion", 48: "acVersionSub", 50: "panelVersion",
  52: "ambientTemp",
  53: "deviceState1", 54: "deviceState2",
  56: "batterySOCx10",
  58: "remainChargeTimeMin",
  59: "pvChargeEnergyTotalH", 60: "pvChargeEnergyTotalL",
  61: "pvChargeEnergyToday",
  71: "remainChargeTime", 72: "remainDischargeTime",
  75: "systemState", 76: "systemState2",
  77: "smartMeterPower", 78: "totalDcDischargePower",
};

const HOLDING_REGISTER_MAP = {
  15: "dcInputType",
  24: "usbOutputCmd", 25: "dcOutputCmd", 26: "acOutputCmd", 27: "ledCmd",
  56: "keySound", 57: "silentCharging",
  59: "usbStandbyTime", 60: "acStandbyTime", 61: "dcStandbyTime",
  62: "screenRestTime", 64: "remoteShutdown",
  66: "dischargeLimitx10", 67: "chargeLimitx10",
  68: "machineUnusedTime",
  84: "lowBatteryNotification",
};

let sseClients = [];
let deviceConnections = {};

function getDeviceConnection(deviceId) {
  const key = deviceId.replace(/:/g, "");
  return deviceConnections[key] || null;
}

function getAllDeviceData() {
  const result = {};
  for (const [key, conn] of Object.entries(deviceConnections)) {
    result[key] = { deviceId: conn.deviceId, data: conn.lastData, connected: !!conn.client };
  }
  return result;
}

function crc16Modbus(data) {
  let crc = 0xFFFF;
  for (let i = 0; i < data.length; i++) {
    crc ^= data[i];
    for (let j = 0; j < 8; j++) {
      if (crc & 1) crc = (crc >> 1) ^ 0xA001;
      else crc >>= 1;
    }
  }
  return crc;
}

function buildModbusReadRequest(slaveAddr, funcCode, startReg, regCount) {
  const buf = Buffer.alloc(8);
  buf[0] = slaveAddr;
  buf[1] = funcCode;
  buf.writeUInt16BE(startReg, 2);
  buf.writeUInt16BE(regCount, 4);
  const crc = crc16Modbus(buf.slice(0, 6));
  buf.writeUInt16BE(crc, 6);
  return buf;
}

function buildModbusWriteRequest(slaveAddr, regAddr, value) {
  const buf = Buffer.alloc(8);
  buf[0] = slaveAddr;
  buf[1] = 0x06;
  buf.writeUInt16BE(regAddr, 2);
  buf.writeUInt16BE(value, 4);
  const crc = crc16Modbus(buf.slice(0, 6));
  buf.writeUInt16BE(crc, 6);
  return buf;
}

function parseModbusResponse(data) {
  if (data.length < 7) return null;
  const slaveAddr = data[0];
  const funcCode = data[1] > 128 ? data[1] - 128 : data[1];
  if (funcCode !== 3 && funcCode !== 4) return null;

  const startReg = (data[2] << 8) | data[3];
  const regCount = (data[4] << 8) | data[5];

  const expectedLen = regCount * 2 + 6 + 2;
  if (data.length < expectedLen) return null;

  const crcData = data.slice(0, data.length - 2);
  const crcReceived = (data[data.length - 2] << 8) | data[data.length - 1];
  const crcCalc = crc16Modbus(crcData);
  if (crcReceived !== crcCalc) return null;

  const registers = [];
  for (let i = 0; i < regCount; i++) {
    const offset = 6 + i * 2;
    registers.push((data[offset] << 8) | data[offset + 1]);
  }

  const regMap = funcCode === 3 ? HOLDING_REGISTER_MAP : INPUT_REGISTER_MAP;
  const named = {};
  for (let i = 0; i < regCount; i++) {
    const regIdx = startReg + i;
    const name = regMap[regIdx];
    if (name) named[name] = registers[i];
  }

  if (funcCode === 4) {
    if (named.batterySOCx10 !== undefined)
      named.mainBattery = named.batterySOCx10 / 10;
    if (named.batteryVoltage !== undefined)
      named.batteryVoltage = named.batteryVoltage / 10;
    if (named.ambientTemp !== undefined)
      named.ambientTemp = named.ambientTemp / 10;
    if (named.usbOutputState !== undefined) named.usbOn = named.usbOutputState > 0;
    if (named.dcOutputState !== undefined) named.dcOn = named.dcOutputState > 0;
    if (named.acOutputState !== undefined) named.acOn = named.acOutputState > 0;
    if (named.ledState !== undefined) named.ledMode = named.ledState;
    if (named.pvChargeEnergyToday !== undefined)
      named.pvEnergyTodayKwh = +(named.pvChargeEnergyToday * 10 / 1000).toFixed(2);
  }

  if (funcCode === 3) {
    if (named.usbOutputCmd !== undefined) named.usbOn = named.usbOutputCmd > 0;
    if (named.dcOutputCmd !== undefined) named.dcOn = named.dcOutputCmd > 0;
    if (named.acOutputCmd !== undefined) named.acOn = named.acOutputCmd > 0;
    if (named.ledCmd !== undefined) named.ledMode = named.ledCmd;
    if (named.lowBatteryNotification !== undefined) {
      named.lowBattNotifyEnabled = (named.lowBatteryNotification >> 8) & 1;
      named.lowBattNotifyThreshold = named.lowBatteryNotification & 0xFF;
    }

  }

  return { slaveAddr, funcCode, startReg, regCount, registers, named };
}

function broadcastSSE(event, data) {
  const msg = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  sseClients = sseClients.filter((c) => !c.destroyed);
  sseClients.forEach((c) => c.write(msg));
}

async function getMqttCredentials(deviceId) {
  const userId = userInfo?.userInfo?._id;
  if (!userId) throw new Error("Not logged in");

  const timestamp = Date.now();
  const d = timestamp % 10;
  const apiSecret = userId.substring(d);
  const sign = crypto.createHash("md5").update(`timestamp=${timestamp}&api_secret=${apiSecret}`).digest("hex");
  const timezoneOffset = -1 * new Date().getTimezoneOffset();

  const result = await invokeFunction("common/emqx.getAccessToken2", {
    sign, timestamp, timezoneOffset, device_id: deviceId,
  });

  if (!result.data) throw new Error("MQTT token failed: " + JSON.stringify(result));
  return result.data;
}

async function connectMqtt(deviceId, modbusAddr, modbusCount) {
  const deviceIdClean = deviceId.replace(/:/g, "");
  disconnectMqttDevice(deviceIdClean);

  const creds = await getMqttCredentials(deviceId);
  const host = creds.mqtt_host || "mqtt.sydpower.com";
  const mqttUsername = creds.access_token;
  const userId = creds.userInfo?._id || userInfo?.userInfo?._id;

  const timestamp = Date.now();
  const d = timestamp % 10;
  const apiSecret = userId.substring(d);
  const signHash = crypto.createHash("md5").update(`timestamp=${timestamp}&api_secret=${apiSecret}`).digest("hex");
  const clientId = `client_${userId}_${signHash}_${timestamp}`;

  const url = `ws://${host}:8083/mqtt`;

  const client = mqtt.connect(url, {
    clientId,
    username: mqttUsername,
    password: "client123",
    clean: true,
    keepalive: 60,
    protocolVersion: 4,
    reconnectPeriod: 3000,
    connectTimeout: 10000,
  });

  const conn = {
    deviceId,
    deviceIdClean,
    modbusAddr,
    modbusCount,
    client,
    lastData: {},
    pollInterval: null,
  };
  deviceConnections[deviceIdClean] = conn;

  const subTopics = [
    `${deviceIdClean}/device/response/state`,
    `${deviceIdClean}/device/response/faultCode`,
    `${deviceIdClean}/device/response/client/+`,
    `${deviceIdClean}/device/webhook`,
  ];

  client.on("connect", () => {
    broadcastSSE("mqtt-status", { connected: true, deviceId });
    client.subscribe(subTopics, { qos: 0 });
    pollDeviceData(deviceIdClean);
    conn.pollInterval = setInterval(() => pollDeviceData(deviceIdClean), 5000);
  });

  client.on("close", () => {
    broadcastSSE("mqtt-status", { connected: false, deviceId });
  });

  client.on("error", (err) => {
    broadcastSSE("mqtt-error", { error: err.message, deviceId });
  });

  client.on("message", (topic, message) => {
    if (topic.includes("/device/response/state")) {
      const state = parseInt(message.toString());
      conn.lastData.mqttState = state;
      broadcastSSE("device-state", { online: !!state, deviceId });
    } else if (topic.includes("/device/webhook")) {
      const status = message.toString();
      broadcastSSE("device-webhook", { status, deviceId });
    } else if (topic.includes("/device/response/client")) {
      const bytes = Array.from(new Uint8Array(message));
      if (bytes.length === 8 && bytes[1] === 0x06) {
        const reg = (bytes[2] << 8) | bytes[3];
        const val = (bytes[4] << 8) | bytes[5];
        broadcastSSE("device-raw", { hex: Buffer.from(message).toString("hex"), info: `Write confirmed: reg ${reg}=${val}`, deviceId });
      } else {
        const parsed = parseModbusResponse(bytes);
        if (parsed) {
          Object.assign(conn.lastData, parsed.named);

          if (parsed.funcCode === 4) {
            const capacityWh = 2048;
            const soc = conn.lastData.mainBattery;
            const outputW = conn.lastData.totalOutputPower || 0;
            const anyOn = conn.lastData.acOn || conn.lastData.dcOn || conn.lastData.usbOn;
            if (soc !== undefined && (outputW > 0 || anyOn)) {
              const totalDrain = outputW * 1.5 + 22;
              parsed.named.remainDischargeHours = Math.round((capacityWh * soc / 100) / totalDrain * 10) / 10;
              conn.lastData.remainDischargeHours = parsed.named.remainDischargeHours;
            }
            const inputW = (conn.lastData.dcChargePower || 0) + (conn.lastData.acChargePower || 0) +
              (conn.lastData.pv1ChargePower || 0) + (conn.lastData.pv2ChargePower || 0);
            const rcMin = conn.lastData.remainChargeTimeMin;
            if (rcMin && rcMin > 0) {
              parsed.named.remainChargeMinutes = rcMin;
              conn.lastData.remainChargeMinutes = rcMin;
            } else if (soc !== undefined && soc < 100 && inputW > 5) {
              const fallbackMin = Math.round((capacityWh * (100 - soc) / 100) / (inputW * 0.85) * 60);
              parsed.named.remainChargeMinutes = fallbackMin;
              conn.lastData.remainChargeMinutes = fallbackMin;
            }
          }

          const nonZero = {};
          parsed.registers.forEach((v, i) => { if (v !== 0) nonZero[parsed.startReg + i] = v; });
          if (parsed.funcCode === 3) {
            [84].forEach(r => {
              const idx = r - parsed.startReg;
              if (idx >= 0 && idx < parsed.registers.length) nonZero[r] = parsed.registers[idx];
            });
          }
          broadcastSSE("device-data", {
            ...parsed.named,
            _fc: parsed.funcCode,
            _registers: nonZero,
            raw: { startReg: parsed.startReg, regCount: parsed.regCount },
            deviceId,
          });
        } else {
          broadcastSSE("device-raw", { hex: Buffer.from(message).toString("hex"), topic, deviceId });
        }
      }
    } else if (topic.includes("/device/response/faultCode")) {
      const bytes = Array.from(new Uint8Array(message));
      broadcastSSE("device-fault", { bytes, deviceId });
    }
  });
}

function pollDeviceData(deviceIdClean) {
  const conn = deviceConnections[deviceIdClean];
  if (!conn || !conn.client) return;
  const topic = `${deviceIdClean}/client/request/data`;
  const fc4Cmd = buildModbusReadRequest(conn.modbusAddr, 4, 0, conn.modbusCount);
  conn.client.publish(topic, fc4Cmd, { qos: 0, retain: false, dup: true });
  setTimeout(() => {
    if (!conn.client) return;
    const fc3Count = Math.max(conn.modbusCount, 86);
    const fc3Cmd = buildModbusReadRequest(conn.modbusAddr, 3, 0, fc3Count);
    conn.client.publish(topic, fc3Cmd, { qos: 0, retain: false, dup: true });
  }, 500);
}

function disconnectMqttDevice(deviceIdClean) {
  const conn = deviceConnections[deviceIdClean];
  if (!conn) return;
  if (conn.pollInterval) {
    clearInterval(conn.pollInterval);
    conn.pollInterval = null;
  }
  if (conn.client) {
    conn.client.end(true);
    conn.client = null;
  }
  delete deviceConnections[deviceIdClean];
}

function disconnectAllMqtt() {
  for (const key of Object.keys(deviceConnections)) {
    disconnectMqttDevice(key);
  }
}

app.get("/api/mqtt/events", (req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
  });
  res.write("event: connected\ndata: {}\n\n");
  sseClients.push(res);
  req.on("close", () => {
    sseClients = sseClients.filter((c) => c !== res);
  });
});

app.post("/api/mqtt/connect", async (req, res) => {
  const { deviceId, modbusAddr, modbusCount } = req.body;
  if (!deviceId) return res.status(400).json({ success: false, error: "deviceId required" });
  if (!uniIdToken) return res.status(401).json({ success: false, error: "Not authenticated" });

  try {
    await connectMqtt(deviceId, modbusAddr || 17, modbusCount || 80);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post("/api/mqtt/disconnect", (req, res) => {
  const { deviceId } = req.body || {};
  if (deviceId) {
    disconnectMqttDevice(deviceId.replace(/:/g, ""));
  } else {
    disconnectAllMqtt();
  }
  res.json({ success: true });
});

app.post("/api/mqtt/poll", (req, res) => {
  const { deviceId } = req.body || {};
  if (deviceId) {
    const key = deviceId.replace(/:/g, "");
    const conn = deviceConnections[key];
    if (!conn) return res.status(400).json({ success: false, error: "Device not connected" });
    pollDeviceData(key);
  } else {
    for (const key of Object.keys(deviceConnections)) {
      pollDeviceData(key);
    }
  }
  res.json({ success: true });
});

app.post("/api/mqtt/control", (req, res) => {
  const { register, value, deviceId } = req.body;
  if (register === undefined || value === undefined) {
    return res.status(400).json({ success: false, error: "register and value required" });
  }

  let conn;
  if (deviceId) {
    conn = deviceConnections[deviceId.replace(/:/g, "")];
  } else {
    const keys = Object.keys(deviceConnections);
    if (keys.length === 1) conn = deviceConnections[keys[0]];
  }
  if (!conn || !conn.client) {
    return res.status(400).json({ success: false, error: "MQTT not connected" });
  }

  console.log(`FC6 write: device=${conn.deviceIdClean} register=${register}, value=${value} (0x${value.toString(16)})`);
  const topic = `${conn.deviceIdClean}/client/request/data`;
  const cmd = buildModbusWriteRequest(conn.modbusAddr, register, value);
  conn.client.publish(topic, cmd, { qos: 0, retain: false, dup: true });
  setTimeout(() => pollDeviceData(conn.deviceIdClean), 500);
  res.json({ success: true });
});

app.get("/api/mqtt/data", (req, res) => {
  const { deviceId } = req.query;
  if (deviceId) {
    const key = deviceId.replace(/:/g, "");
    const conn = deviceConnections[key];
    if (!conn) return res.json({ success: true, data: {}, connected: false });
    return res.json({ success: true, data: conn.lastData, connected: !!conn.client });
  }
  const connected = Object.keys(deviceConnections).length > 0;
  const allData = getAllDeviceData();
  const firstKey = Object.keys(deviceConnections)[0];
  const data = firstKey ? deviceConnections[firstKey].lastData : {};
  res.json({ success: true, data, connected, devices: allData });
});

app.listen(PORT, async () => {
  console.log(`Fossibot Control Panel running at http://localhost:${PORT}`);
  await autoLogin();
});
