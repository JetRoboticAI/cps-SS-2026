require("dotenv").config();

const express = require("express");
const http = require("http");
const mqtt = require("mqtt");
const { Server } = require("socket.io");
const { InfluxDB, Point } = require("@influxdata/influxdb-client");

const PORT = Number(process.env.PORT || 3000);
const MQTT_URL = process.env.MQTT_URL || "mqtt://localhost:1883";
const BASE_TOPIC = process.env.MQTT_BASE_TOPIC || "slotsense";
const INFLUX_VERSION = process.env.INFLUX_VERSION || "1";
const INFLUX_URL = process.env.INFLUX_URL || "http://localhost:8086";
const INFLUX_DATABASE = process.env.INFLUX_DATABASE || process.env.INFLUX_BUCKET || "parking";

const app = express();
const server = http.createServer(app);
const io = new Server(server);

const dashboardState = {
  node: "offline",
  gate: {
    state: "closed",
    reason: "waiting for MQTT data",
    servo_angle: 0,
    ts: null,
  },
  slots: {},
  lastEvent: null,
};

let writeApi = null;
let influxV1Enabled = false;

if (INFLUX_VERSION === "2" && process.env.INFLUX_URL && process.env.INFLUX_TOKEN && process.env.INFLUX_ORG && process.env.INFLUX_BUCKET) {
  const influx = new InfluxDB({
    url: process.env.INFLUX_URL,
    token: process.env.INFLUX_TOKEN,
  });
  writeApi = influx.getWriteApi(process.env.INFLUX_ORG, process.env.INFLUX_BUCKET, "ns");
  console.log(`[influx] writing to InfluxDB 2 bucket ${process.env.INFLUX_BUCKET}`);
} else if (INFLUX_VERSION === "1") {
  influxV1Enabled = true;
  console.log(`[influx] writing to InfluxDB 1 database ${INFLUX_DATABASE}`);
} else {
  console.log("[influx] not configured; dashboard will run without database writes");
}

app.use(express.static("public"));

const mqttClient = mqtt.connect(MQTT_URL, {
  username: process.env.MQTT_USERNAME || undefined,
  password: process.env.MQTT_PASSWORD || undefined,
  clientId: `slotsense-web-${Math.random().toString(16).slice(2)}`,
  clean: true,
  reconnectPeriod: 2000,
});

function publishState() {
  io.emit("state", dashboardState);
}

function parseJson(payload) {
  try {
    return JSON.parse(payload.toString());
  } catch (error) {
    return null;
  }
}

function escapeInfluxTag(value) {
  return String(value ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/,/g, "\\,")
    .replace(/ /g, "\\ ")
    .replace(/=/g, "\\=");
}

function escapeInfluxString(value) {
  return String(value ?? "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function formatInfluxField(value) {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return `"${escapeInfluxString(value)}"`;
}

function toInfluxLine(measurement, tags, fields) {
  const tagText = Object.entries(tags)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${escapeInfluxTag(key)}=${escapeInfluxTag(value)}`)
    .join(",");
  const fieldText = Object.entries(fields)
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([key, value]) => `${escapeInfluxTag(key)}=${formatInfluxField(value)}`)
    .join(",");

  return `${escapeInfluxTag(measurement)}${tagText ? `,${tagText}` : ""} ${fieldText}`;
}

function writeInfluxV1(line) {
  if (!influxV1Enabled || !line) return;

  const url = new URL("/write", INFLUX_URL);
  url.searchParams.set("db", INFLUX_DATABASE);

  const req = http.request(url, { method: "POST" }, (res) => {
    if (res.statusCode >= 300) {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        console.error(`[influx] write failed ${res.statusCode}: ${body}`);
      });
    }
  });

  req.on("error", (error) => {
    console.error(`[influx] write error: ${error.message}`);
  });
  req.end(line);
}

function queryInfluxV1(query) {
  return new Promise((resolve, reject) => {
    const url = new URL("/query", INFLUX_URL);
    url.searchParams.set("db", INFLUX_DATABASE);
    url.searchParams.set("q", query);

    const req = http.get(url, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        if (res.statusCode >= 300) {
          reject(new Error(`Influx query failed ${res.statusCode}: ${body}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(error);
        }
      });
    });

    req.on("error", reject);
  });
}

app.get("/api/influx/latest", async (_req, res) => {
  if (INFLUX_VERSION !== "1") {
    res.status(400).json({ error: "Influx latest endpoint is configured for InfluxDB 1.x" });
    return;
  }

  try {
    const data = await queryInfluxV1(
      "SELECT * FROM parking_gate ORDER BY time DESC LIMIT 5; " +
      "SELECT * FROM parking_slot ORDER BY time DESC LIMIT 5"
    );
    res.json({
      database: INFLUX_DATABASE,
      url: INFLUX_URL,
      data,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

function writeSlotPoint(slot) {
  const state = String(slot.state || "").toLowerCase();
  const occupied = Boolean(slot.occupied) || state === "occupied";
  const spaceAvailable = Boolean(slot.space_available) || ["available", "vacant", "free"].includes(state);
  const fields = {
    state: slot.state || "unknown",
    occupied,
    space_available: spaceAvailable,
    led_on: Boolean(slot.led_on),
    led_blinking: Boolean(slot.led_blinking),
  };

  if (typeof slot.distance_cm === "number") {
    fields.distance_cm = slot.distance_cm;
  }
  if (typeof slot.spot_distance_cm === "number") {
    fields.spot_distance_cm = slot.spot_distance_cm;
  }

  writeInfluxV1(toInfluxLine("parking_slot", { slot_id: slot.slot_id || "A1" }, fields));

  if (!writeApi) return;

  const point = new Point("parking_slot")
    .tag("slot_id", slot.slot_id || "A1")
    .stringField("state", fields.state)
    .booleanField("occupied", fields.occupied)
    .booleanField("space_available", fields.space_available)
    .booleanField("led_on", fields.led_on)
    .booleanField("led_blinking", fields.led_blinking);

  if (typeof fields.distance_cm === "number") {
    point.floatField("distance_cm", fields.distance_cm);
  }
  if (typeof fields.spot_distance_cm === "number") {
    point.floatField("spot_distance_cm", fields.spot_distance_cm);
  }

  writeApi.writePoint(point);
}

function writeGatePoint(gate) {
  const fields = {
    state: gate.state || "unknown",
    reason: gate.reason || "",
    car_detected: Boolean(gate.car_detected),
    servo_angle: Number(gate.servo_angle || 0),
  };

  if (typeof gate.gate_distance_cm === "number") {
    fields.gate_distance_cm = gate.gate_distance_cm;
  }

  writeInfluxV1(toInfluxLine("parking_gate", {}, fields));

  if (!writeApi) return;

  const point = new Point("parking_gate")
    .stringField("state", fields.state)
    .stringField("reason", fields.reason)
    .booleanField("car_detected", fields.car_detected)
    .floatField("servo_angle", fields.servo_angle);

  if (typeof fields.gate_distance_cm === "number") {
    point.floatField("gate_distance_cm", fields.gate_distance_cm);
  }

  writeApi.writePoint(point);
}

mqttClient.on("connect", () => {
  console.log(`[mqtt] connected to ${MQTT_URL}`);
  mqttClient.subscribe([
    `${BASE_TOPIC}/node/status`,
    `${BASE_TOPIC}/slot/+/status`,
    `${BASE_TOPIC}/gate/status`,
  ]);
});

mqttClient.on("reconnect", () => {
  console.log("[mqtt] reconnecting");
});

mqttClient.on("error", (error) => {
  console.error("[mqtt]", error.message);
});

mqttClient.on("message", (topic, payload) => {
  const now = new Date().toISOString();

  if (topic === `${BASE_TOPIC}/node/status`) {
    dashboardState.node = payload.toString();
    dashboardState.lastEvent = { ts: now, text: `Node is ${dashboardState.node}` };
    publishState();
    return;
  }

  if (topic === `${BASE_TOPIC}/gate/status`) {
    const gate = parseJson(payload);
    if (!gate) return;
    dashboardState.node = "online";
    dashboardState.gate = { ...dashboardState.gate, ...gate, ts: gate.ts || now };
    dashboardState.lastEvent = {
      ts: now,
      text: `Gate ${dashboardState.gate.state} (${dashboardState.gate.reason || "sensor update"})`,
    };
    writeGatePoint(dashboardState.gate);
    publishState();
    return;
  }

  const slotMatch = topic.match(new RegExp(`^${BASE_TOPIC}/slot/([^/]+)/status$`));
  if (slotMatch) {
    const slot = parseJson(payload);
    if (!slot) return;
    dashboardState.node = "online";
    const slotId = slot.slot_id || slotMatch[1];
    const slotState = String(slot.state || "").toLowerCase();
    const occupied = Boolean(slot.occupied) || slotState === "occupied";
    const spaceAvailable = Boolean(slot.space_available) || ["available", "vacant", "free"].includes(slotState);
    dashboardState.slots[slotId] = {
      ...slot,
      occupied,
      space_available: spaceAvailable,
      slot_id: slotId,
      ts: slot.ts || now,
    };
    dashboardState.lastEvent = {
      ts: now,
      text: `${slotId} is ${slot.state}; LED ${slot.led_on || spaceAvailable ? "on" : "off"}`,
    };
    writeSlotPoint(dashboardState.slots[slotId]);
    publishState();
  }
});

io.on("connection", (socket) => {
  socket.emit("state", dashboardState);

  socket.on("gate-command", (command) => {
    const allowed = new Set(["force_open", "force_close", "auto"]);
    if (!allowed.has(command)) return;

    mqttClient.publish(`${BASE_TOPIC}/gate/command`, JSON.stringify({
      command,
      source: "web",
      ts: new Date().toISOString(),
    }));
  });
});

async function shutdown() {
  console.log("[server] shutting down");
  mqttClient.end(true);
  if (writeApi) {
    await writeApi.close();
  }
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1000).unref();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

server.listen(PORT, () => {
  console.log(`[web] http://localhost:${PORT}`);
});
