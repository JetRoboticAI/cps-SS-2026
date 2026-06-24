import RPi.GPIO as GPIO
import time
import json
from datetime import datetime
from gpiozero import Servo
import paho.mqtt.client as mqtt
import random

# ==================================================
# MQTT CONFIG
# ==================================================

BROKER = "broker.hivemq.com"
PORT = 1883
# TOPIC = "kg-test"

TOPIC_SPOT_STATUS = "parking/spot/status"
TOPIC_GATE_EVENT = "parking/gate/event"

client = mqtt.Client(client_id="mac-publisher-1")
client.connect(BROKER, PORT, 60)
client.loop_start()

# ==================================================
# GPIO PINS
# ==================================================

# Gate Ultrasonic Sensor
GATE_TRIG = 12
GATE_ECHO = 25

# Parking Spot 1 Sensor
SPOT1_TRIG = 6
SPOT1_ECHO = 26

# Parking Spot 2 Sensor
SPOT2_TRIG = 13
SPOT2_ECHO = 19

# LE
LED1 = 20
LED2 = 21

# Servo
servo = Servo(23)

# ==================================================
# GPIO SETUP
# ==================================================

GPIO.setmode(GPIO.BCM)

sensor_pins = [
    (GATE_TRIG, GATE_ECHO),
    (SPOT1_TRIG, SPOT1_ECHO),
    (SPOT2_TRIG, SPOT2_ECHO)
]

for trig, echo in sensor_pins:
    GPIO.setup(trig, GPIO.OUT)
    GPIO.setup(echo, GPIO.IN)
    GPIO.output(trig, False)

GPIO.setup(LED1, GPIO.OUT)
GPIO.setup(LED2, GPIO.OUT)

time.sleep(2)

# ==================================================
# MQTT HELPERS
# ==================================================

def publish_spot_status(spot_id, status):

    payload = {
        "spotId": spot_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }

    client.publish(
        TOPIC_SPOT_STATUS,
        json.dumps(payload)
    )

    print(f"MQTT -> Spot {spot_id}: {status}")


def publish_gate_event(status, availableSpots, reason=None):

    payload = {
        "status": status,
        "availableSpots": availableSpots,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }

    client.publish(
        TOPIC_GATE_EVENT,
        json.dumps(payload)
    )

    print(f"MQTT -> Gate Event: {status}")


# ==================================================
# ULTRASONIC SENSOR
# ==================================================

def get_distance(trig, echo):


    GPIO.output(trig, True)
    time.sleep(0.00001)
    GPIO.output(trig, False)

    pulse_start = time.time()
    pulse_end = time.time()

    timeout = time.time() + 0.5

    while GPIO.input(echo) == 0:
        pulse_start = time.time()

        if time.time() > timeout:
            return 999

    timeout = time.time() + 0.5

    while GPIO.input(echo) == 1:
        pulse_end = time.time()

        if time.time() > timeout:
            return 999

    pulse_duration = pulse_end - pulse_start

    distance = pulse_duration * 17150

    return round(distance, 1)
    # return random.randint(0, 20)


# ==================================================
# SERVO
# ==================================================



def open_gate():
    print("Gate Opening (90°)")
    servo.value = 0  # 90°
    time.sleep(5)

    print("Gate Closing (0°)")
    servo.value = -1  # 0°


# ==================================================
# STATUS TRACKING
# ==================================================

last_spot1_status = None
last_spot2_status = None

# ==================================================
# MAIN LOOP
# ==================================================

try:
    while True:

        # ------------------------------------------
        # Spot 1
        # ------------------------------------------

        spot1_distance = get_distance(
            SPOT1_TRIG,
            SPOT1_ECHO
        )

        print("Spot1 distance: ",spot1_distance)

        spot1_status = (
            "occupied"
            if spot1_distance < 5
            else "available"
        )

        if spot1_status == "occupied":
            GPIO.output(LED1, GPIO.LOW)
            print("Spot 1: LED OFF")
        else:
            GPIO.output(LED1, GPIO.HIGH)
            print("Spot 1: LED ON")

        if spot1_status != last_spot1_status:
            publish_spot_status(1, spot1_status)
            # print("Spot1 status published", spot1_status)
            last_spot1_status = spot1_status

        # ------------------------------------------
        # Spot 2
        # ------------------------------------------

        spot2_distance = get_distance(
            SPOT2_TRIG,
            SPOT2_ECHO
        )

        print("spot2 distance",spot2_distance)

        spot2_status = (
            "occupied"
            if spot2_distance < 5
            else "available"
        )

        if spot2_status == "occupied":
            GPIO.output(LED2, GPIO.LOW)
            print("Spot 2: LED OFF")
        else:
            GPIO.output(LED2, GPIO.HIGH)
            print("Spot 2: LED ON")

        if spot2_status != last_spot2_status:
            publish_spot_status(2, spot2_status)
            # print("Spot2 status published", spot2_status)
            last_spot2_status = spot2_status

        # ------------------------------------------
        # Gate Sensor
        # ------------------------------------------

        gate_distance = get_distance(
            GATE_TRIG,
            GATE_ECHO
        )

        print(
            f"Gate={gate_distance}cm | "
            f"Spot1={spot1_status} | "
            f"Spot2={spot2_status}"
        )

        if gate_distance < 10:
            available_spots = 2
            if spot1_status == "occupied":
                available_spots -= 1
            if spot2_status == "occupied":
                available_spots -= 1

            if (
                available_spots == 0
            ):

                publish_gate_event(
                    "AccessDenied",
                    0,
                    "Parking Full"
                )

                print(
                    "Access Denied(Parking Full)"
                )

            else:

                publish_gate_event(
                    "AccessGranted",
                    available_spots

                )
                print("Gate open activated")
                open_gate()

        time.sleep(2)

except KeyboardInterrupt:

    print("Stopping Program")

finally:
    servo.stop()

    client.loop_stop()
    client.disconnect()

    GPIO.cleanup()