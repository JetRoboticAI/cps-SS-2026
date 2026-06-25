#!/usr/bin/env python3
"""
SlotSense Raspberry Pi controller.

Core logic:
- Ultrasonic sensor 1 checks the parking spot.
- If spot distance is more than 50 cm, the parking spot is available.
- Ultrasonic sensor 2 checks whether a car is at the gate.
- When a car reaches the gate, the code checks the parking spot sensor.
- If the spot is available, the servo opens the gate.
- LED is ON when the parking spot is available, OFF when occupied.
"""

import json
import os
import signal
import socket
import sys
import time
import traceback
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

# -----------------------------
# MQTT configuration
# -----------------------------
MQTT_HOST = os.environ.get("MQTT_HOST", "172.17.42.185")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "slotsense-pi-two-ultrasonic")
BASE_TOPIC = os.environ.get("MQTT_BASE_TOPIC", "slotsense")

# -----------------------------
# GPIO pin configuration
# Change these if your wiring is different.
# -----------------------------
SPOT_TRIG = 5
SPOT_ECHO = 6

GATE_TRIG = 23
GATE_ECHO = 24

LED = 27
SERVO = 18

# -----------------------------
# Logic thresholds
# -----------------------------
SLOT_ID = "A1"
POLL_INTERVAL_S = 0.5

# Parking spot is available when the spot sensor reads more than 50 cm.
SPOT_AVAILABLE_THRESHOLD_CM = 50.0

# Car is at the gate when the gate sensor reads this distance or less.
GATE_CAR_THRESHOLD_CM = 25.0

SERVO_CLOSED_DUTY = 2.5
SERVO_OPEN_DUTY = 7.5
SERVO_CLOSED_ANGLE = 0
SERVO_OPEN_ANGLE = 90
MQTT_RETRY_DELAY_S = 3

running = True
gate_open = False
auto_mode = True


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(SPOT_TRIG, GPIO.OUT)
    GPIO.setup(SPOT_ECHO, GPIO.IN)
    GPIO.setup(GATE_TRIG, GPIO.OUT)
    GPIO.setup(GATE_ECHO, GPIO.IN)
    GPIO.setup(LED, GPIO.OUT)
    GPIO.setup(SERVO, GPIO.OUT)

    GPIO.output(SPOT_TRIG, False)
    GPIO.output(GATE_TRIG, False)
    GPIO.output(LED, False)


def read_distance_cm(trigger_pin, echo_pin):
    GPIO.output(trigger_pin, False)
    time.sleep(0.03)

    GPIO.output(trigger_pin, True)
    time.sleep(0.00001)
    GPIO.output(trigger_pin, False)

    wait_start = time.time()
    pulse_start = wait_start
    while GPIO.input(echo_pin) == 0:
        pulse_start = time.time()
        if pulse_start - wait_start > 0.05:
            return None

    wait_end = time.time()
    pulse_end = wait_end
    while GPIO.input(echo_pin) == 1:
        pulse_end = time.time()
        if pulse_end - wait_end > 0.05:
            return None

    pulse_duration = pulse_end - pulse_start
    return round(pulse_duration * 17150, 1)


def set_servo(servo, duty_cycle):
    servo.ChangeDutyCycle(duty_cycle)
    time.sleep(0.6)
    servo.ChangeDutyCycle(0)


def open_gate(servo):
    global gate_open
    if gate_open:
        return
    set_servo(servo, SERVO_OPEN_DUTY)
    gate_open = True


def close_gate(servo):
    global gate_open
    if not gate_open:
        return
    set_servo(servo, SERVO_CLOSED_DUTY)
    gate_open = False


def publish_json(client, topic, payload, retain=True):
    client.publish(topic, json.dumps(payload), qos=0, retain=retain)


def publish_slot(client, spot_distance_cm, spot_available):
    publish_json(client, f"{BASE_TOPIC}/slot/{SLOT_ID}/status", {
        "slot_id": SLOT_ID,
        "state": "available" if spot_available else "occupied",
        "occupied": not spot_available,
        "space_available": spot_available,
        "distance_cm": spot_distance_cm,
        "spot_distance_cm": spot_distance_cm,
        "led_on": spot_available,
        "led_blinking": False,
        "sensor": "spot_ultrasonic",
        "available_rule": "spot distance > 50 cm",
        "ts": now_iso(),
    })


def publish_gate(client, state, reason, car_at_gate, gate_distance_cm):
    publish_json(client, f"{BASE_TOPIC}/gate/status", {
        "state": state,
        "reason": reason,
        "car_detected": car_at_gate,
        "gate_distance_cm": gate_distance_cm,
        "servo_angle": SERVO_OPEN_ANGLE if gate_open else SERVO_CLOSED_ANGLE,
        "sensor": "gate_ultrasonic",
        "car_rule": "gate distance <= 25 cm",
        "ts": now_iso(),
    })


def create_mqtt_client(userdata):
    if hasattr(mqtt, "CallbackAPIVersion"):
        try:
            return mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=MQTT_CLIENT_ID,
                userdata=userdata,
            )
        except (TypeError, ValueError):
            pass

    return mqtt.Client(client_id=MQTT_CLIENT_ID, userdata=userdata)


def mqtt_connected(return_code):
    return return_code == 0 or str(return_code).lower() == "success"


def on_connect(client, _userdata, _flags, return_code, *_extra):
    if mqtt_connected(return_code):
        print(f"[mqtt] connected to {MQTT_HOST}:{MQTT_PORT}")
        client.publish(f"{BASE_TOPIC}/node/status", "online", qos=1, retain=True)
        client.subscribe(f"{BASE_TOPIC}/gate/command")
    else:
        print(f"[mqtt] connection failed: {return_code}")


def on_message(client, userdata, message):
    global auto_mode

    servo = userdata["servo"]
    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {"command": message.payload.decode("utf-8").strip()}

    command = payload.get("command")
    if command == "force_open":
        auto_mode = False
        open_gate(servo)
        publish_gate(client, "open", "forced open from web dashboard", True, None)
    elif command == "force_close":
        auto_mode = False
        close_gate(servo)
        publish_gate(client, "closed", "forced closed from web dashboard", False, None)
    elif command == "auto":
        auto_mode = True
        publish_gate(client, "closed", "automatic two-ultrasonic mode enabled", False, None)


def stop(_signum, _frame):
    global running
    running = False


def connect_mqtt_with_retry(client):
    while running:
        try:
            print(f"[mqtt] connecting to {MQTT_HOST}:{MQTT_PORT} ...")
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            return True
        except (ConnectionRefusedError, OSError, socket.timeout) as error:
            print(f"[mqtt] connection failed: {error}")
            print(f"[mqtt] retrying in {MQTT_RETRY_DELAY_S} seconds")
            time.sleep(MQTT_RETRY_DELAY_S)

    return False


def main():
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print("[node] booting SlotSense two-ultrasonic controller")
    print(f"[node] MQTT_HOST={MQTT_HOST} MQTT_PORT={MQTT_PORT}")

    setup_gpio()

    servo = GPIO.PWM(SERVO, 50)
    servo.start(0)

    client = create_mqtt_client({"servo": servo})
    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(f"{BASE_TOPIC}/node/status", "offline", qos=1, retain=True)
    if not connect_mqtt_with_retry(client):
        return 1
    client.loop_start()

    try:
        print("[node] SlotSense two-ultrasonic controller started")
        print(f"[node] spot available when distance > {SPOT_AVAILABLE_THRESHOLD_CM} cm")
        print(f"[node] car at gate when distance <= {GATE_CAR_THRESHOLD_CM} cm")

        while running:
            spot_distance_cm = read_distance_cm(SPOT_TRIG, SPOT_ECHO)
            gate_distance_cm = read_distance_cm(GATE_TRIG, GATE_ECHO)

            spot_available = (
                spot_distance_cm is not None
                and spot_distance_cm > SPOT_AVAILABLE_THRESHOLD_CM
            )
            car_at_gate = (
                gate_distance_cm is not None
                and gate_distance_cm <= GATE_CAR_THRESHOLD_CM
            )

            GPIO.output(LED, spot_available)

            if auto_mode:
                if car_at_gate and spot_available:
                    open_gate(servo)
                    gate_state = "open"
                    reason = "car detected at gate and parking spot is available"
                else:
                    close_gate(servo)
                    gate_state = "closed"
                    if car_at_gate and not spot_available:
                        reason = "car detected at gate but parking spot is occupied"
                    elif not car_at_gate and spot_available:
                        reason = "parking spot available; waiting for car at gate"
                    else:
                        reason = "parking spot occupied; no gate entry"

                publish_gate(client, gate_state, reason, car_at_gate, gate_distance_cm)

            publish_slot(client, spot_distance_cm, spot_available)

            print(
                "spot_distance=",
                spot_distance_cm,
                "spot_available=",
                spot_available,
                "| gate_distance=",
                gate_distance_cm,
                "car_at_gate=",
                car_at_gate,
                "| gate_open=",
                gate_open,
            )
            time.sleep(POLL_INTERVAL_S)

    finally:
        try:
            client.publish(f"{BASE_TOPIC}/node/status", "offline", qos=1, retain=True)
        except Exception:
            pass
        time.sleep(0.2)
        client.loop_stop()
        client.disconnect()
        servo.stop()
        GPIO.output(LED, False)
        GPIO.cleanup()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("[fatal] SlotSense stopped because of this error:")
        traceback.print_exc()
        sys.exit(1)
