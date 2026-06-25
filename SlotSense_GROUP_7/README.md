# SlotSense UI Platform

## MQTT + InfluxDB Web Application

This project now includes a live MQTT web application for the parking gate system.

New files:

- `slotsense_mqtt_pi.py` - Raspberry Pi controller using two ultrasonic sensors, LED, servo motor, and MQTT
- `server.js` - Node.js MQTT bridge, Socket.IO dashboard server, and optional InfluxDB writer
- `public/index.html` - web dashboard showing car detection, gate open/closed state, LED state, servo angle, and data flow
- `public/app.js` - browser-side live dashboard logic
- `public/styles.css` - dashboard styling
- `nodered_slotsense_flow.json` - starter Node-RED MQTT flow for formatting slot/gate points
- `.env.example` - MQTT and InfluxDB settings

System behavior:

- Gate ultrasonic sensor detects whether a car is waiting at the gate.
- Spot ultrasonic sensor detects whether the parking space is available.
- If the gate sensor detects a car and the spot sensor says space is available, the servo rotates to open the gate.
- The dashboard shows `Gate is open` when the servo is open.
- The LED stays ON while a space is available and turns OFF when occupied.
- MQTT messages are published under the `slotsense` topic tree.
- The Node.js server writes readings to InfluxDB when InfluxDB credentials are configured.

MQTT topics:

- `slotsense/node/status` - `online` or `offline`
- `slotsense/slot/A1/status` - slot state, distance, availability, LED state
- `slotsense/gate/status` - gate state, servo angle, and car detection
- `slotsense/gate/command` - web commands: `force_open`, `force_close`, `auto`

Run the MQTT web app:

```bash
cp .env.example .env
npm install
npm start
```

Then open:

- `http://localhost:3000`

Run the Raspberry Pi controller:

```bash
pip3 install -r requirements.txt
MQTT_HOST=<broker-ip-address> python3 slotsense_mqtt_pi.py
```

Default GPIO mapping for `slotsense_mqtt_pi.py`:

- `GPIO 23` -> gate ultrasonic `TRIG`
- `GPIO 24` -> gate ultrasonic `ECHO`
- `GPIO 5` -> spot ultrasonic `TRIG`
- `GPIO 6` -> spot ultrasonic `ECHO`
- `GPIO 27` -> LED
- `GPIO 18` -> servo signal

Default thresholds:

- Gate car detected when gate distance is `25 cm` or less.
- Spot available when spot distance is more than `50 cm`.

Change these values at the top of `slotsense_mqtt_pi.py` if your physical layout needs different pins or distances.

InfluxDB 1.x is supported by default. The dashboard writes to:

- URL: `http://localhost:8086`
- Database: `parking`

Use these environment values when running the dashboard:

```bash
INFLUX_VERSION=1
INFLUX_URL=http://localhost:8086
INFLUX_DATABASE=parking
```

InfluxDB 2.x is also supported by setting `INFLUX_VERSION=2` and providing `INFLUX_TOKEN`, `INFLUX_ORG`, and `INFLUX_BUCKET`.

For Node-RED, import `nodered_slotsense_flow.json`, then add your preferred InfluxDB output node after the two formatter nodes.

This project now includes two browser-based interfaces for your Raspberry Pi parking system.

## Pages

- `index.html` - operator dashboard for staff or admin use
- `customer.html` - customer-facing screen for drivers
- `style.css` - operator dashboard styling
- `customer.css` - customer UI styling
- `app.js` - operator dashboard PubNub logic
- `customer.js` - customer UI PubNub logic
- `slotsense_mqtt_pi.py` - Raspberry Pi final controller script with ultrasonic sensor, IR sensor, LED, servo, and buzzer
- `requirements.txt` - Python package requirements for the Raspberry Pi app

