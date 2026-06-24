const mqtt = require("mqtt");
const mysql = require("mysql2");

// =========================
// MYSQL
// =========================

const db = mysql.createConnection({
    host: "localhost",
    user: "root",
    password: "",
    database: "parking_system"
});

db.connect(err => {
    if (err) {
        console.error(err);
        return;
    }

    console.log("Connected to MySQL");
});

// =========================
// MQTT
// =========================

const client = mqtt.connect("mqtt://broker.hivemq.com");

client.on("connect", () => {
    console.log("Connected to MQTT");

    client.subscribe("parking/spot/status");
    client.subscribe("parking/gate/event");
});

client.on("message", (topic, message) => {

    try {
        const data = JSON.parse(message.toString());

        console.log(topic, data);

        if (topic === "parking/spot/status") {

            const sql = `
                INSERT INTO parking_spot_status
                (spot_id, status, event_time)
                VALUES (?, ?, ?)
            `;

            db.query(
                sql,
                [
                    data.spotId,
                    data.status,
                    data.timestamp
                ]
            );
        }

        if (topic === "parking/gate/event") {

            const sql = `
                INSERT INTO gate_events
                (status, available_spots, reason, event_time)
                VALUES (?, ?, ?, ?)
            `;

            db.query(
                sql,
                [
                    data.status,
                    data.availableSpots,
                    data.reason,
                    data.timestamp
                ]
            );
        }

        

    } catch (err) {
        console.error("Invalid JSON:", err);
    }
});