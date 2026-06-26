import RPi.GPIO as GPIO
import time
import json
import csv
import os
from datetime import datetime
import paho.mqtt.client as mqtt


# =========================
# PIN CONFIG
# =========================
TRIG = 23
ECHO = 24

GREEN_LED = 17
YELLOW_LED = 27
RED_LED = 22

BUZZER = 18


# =========================
# MQTT CONFIG
# =========================
MQTT_BROKER = "10.232.115.251"
MQTT_PORT = 1883


MQTT_TOPIC = "garage/parking"
CLIENT_ID = "raspberry-pi-parking-assistant"


# =========================
# CSV CONFIG
# =========================
CSV_FILE = "garage_parking_log.csv"


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(TRIG, GPIO.OUT)
    GPIO.setup(ECHO, GPIO.IN)

    GPIO.setup(GREEN_LED, GPIO.OUT)
    GPIO.setup(YELLOW_LED, GPIO.OUT)
    GPIO.setup(RED_LED, GPIO.OUT)

    GPIO.setup(BUZZER, GPIO.OUT)

    GPIO.output(TRIG, GPIO.LOW)
    GPIO.output(GREEN_LED, GPIO.LOW)
    GPIO.output(YELLOW_LED, GPIO.LOW)
    GPIO.output(RED_LED, GPIO.LOW)
    GPIO.output(BUZZER, GPIO.LOW)

    time.sleep(0.5)


def setup_csv():
    file_exists = os.path.exists(CSV_FILE)

    if not file_exists:
        with open(CSV_FILE, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["time", "distance", "status"])


def save_to_csv(timestamp, distance, status):
    with open(CSV_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, distance, status])


def setup_mqtt():
    client = mqtt.Client(client_id=CLIENT_ID)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)

    # Start the network loop in the background to handle MQTT traffic
    client.loop_start()

    return client


def measure_distance():
    """
    Measures distance using the HC-SR04 ultrasonic sensor.
    Returns:
        float: Distance in centimeters.
        None: If the reading fails/times out.
    """

    GPIO.output(TRIG, GPIO.LOW)
    time.sleep(0.02)

    # Send a 10-microsecond trigger pulse
    GPIO.output(TRIG, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(TRIG, GPIO.LOW)

    timeout_start = time.time()

    # Wait for ECHO to go HIGH
    while GPIO.input(ECHO) == GPIO.LOW:
        pulse_start = time.time()

        if pulse_start - timeout_start > 0.03:
            return None

    timeout_start = time.time()

    # Wait for ECHO to go LOW
    while GPIO.input(ECHO) == GPIO.HIGH:
        pulse_end = time.time()

        if pulse_end - timeout_start > 0.03:
            return None

    pulse_duration = pulse_end - pulse_start

    # Speed of sound is approx. 34300 cm/s; divide by 2 for the round-trip distance
    distance = pulse_duration * 34300 / 2

    return round(distance, 2)


def get_status(distance):
    if distance is None:
        return "Invalid"

    if distance > 100:
        return "Safe"
    elif 30 <= distance <= 100:
        return "Caution"
    else:
        return "Danger"


def turn_off_all_outputs():
    GPIO.output(GREEN_LED, GPIO.LOW)
    GPIO.output(YELLOW_LED, GPIO.LOW)
    GPIO.output(RED_LED, GPIO.LOW)
    GPIO.output(BUZZER, GPIO.LOW)


def control_outputs(status):
    """
    Controls LEDs and the buzzer based on current safety status:
    - Safe: Green LED ON, buzzer OFF
    - Caution: Yellow LED ON, low-frequency/long-interval buzzing
    - Danger: Red LED ON, high-frequency/short-interval buzzing
    """

    turn_off_all_outputs()

    if status == "Safe":
        GPIO.output(GREEN_LED, GPIO.HIGH)
        time.sleep(0.5)

    elif status == "Caution":
        GPIO.output(YELLOW_LED, GPIO.HIGH)

        # Low-frequency, long-interval beep
        GPIO.output(BUZZER, GPIO.HIGH)
        time.sleep(0.15)
        GPIO.output(BUZZER, GPIO.LOW)
        time.sleep(0.85)

    elif status == "Danger":
        GPIO.output(RED_LED, GPIO.HIGH)

        # High-frequency, short-interval beep
        GPIO.output(BUZZER, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(BUZZER, GPIO.LOW)
        time.sleep(0.2)

    else:
        # Invalid reading
        GPIO.output(BUZZER, GPIO.LOW)
        time.sleep(0.5)


def publish_mqtt(client, timestamp, distance, status):
    payload = {
        "time": timestamp,
        "distance": distance,
        "status": status
    }

    client.publish(
        MQTT_TOPIC,
        json.dumps(payload),
        qos=0,
        retain=False
    )


def main():
    print("Smart Garage Parking Assistance System Started")

    setup_gpio()
    setup_csv()
    mqtt_client = setup_mqtt()

    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            distance = measure_distance()
            status = get_status(distance)

            # Print parameters to the console
            print(f"time={timestamp}, distance={distance}, status={status}")

            # Save data to CSV log
            save_to_csv(timestamp, distance, status)

            # Publish payload to Node-RED via MQTT
            publish_mqtt(mqtt_client, timestamp, distance, status)

            # Control LEDs and buzzer based on status
            control_outputs(status)

    except KeyboardInterrupt:
        print("\nProgram stopped by user.")

    finally:
        turn_off_all_outputs()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        GPIO.cleanup()
        print("GPIO cleaned up. MQTT disconnected.")


if __name__ == "__main__":
    main()