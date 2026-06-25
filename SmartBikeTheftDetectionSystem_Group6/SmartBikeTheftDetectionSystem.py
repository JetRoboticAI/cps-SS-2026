#!/usr/bin/env python3
"""
=============================================================
  Bike Theft Detection System 
  SEP769 - Group 6
  Components: Raspberry Pi 3, GY-9250/MPU-9250, SW-420,
              Piezo Buzzer, Red LED, Green LED, Push Button
=============================================================
"""

import RPi.GPIO as GPIO
import smbus2, time, math, json, csv, os
import paho.mqtt.client as mqtt

# ─────────────────────────────────────────────────────────────
#  MQTT CONFIGURATION
# ─────────────────────────────────────────────────────────────
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT   = 1883
MQTT_TOPIC  = "sep769/group6/bike/alert"

# ─────────────────────────────────────────────────────────────
#  LOG FILE CONFIGURATION
# ─────────────────────────────────────────────────────────────
LOG_FILE = os.path.expanduser("~/Desktop/CPS/bike_event_log.csv")

# ─────────────────────────────────────────────────────────────
#  PIN CONFIGURATION  (BCM numbering)
# ─────────────────────────────────────────────────────────────
GPIO17_VIB  = 17   # SW-420 vibration sensor  →  Pin 11
GPIO22_BUZ  = 22   # Piezo buzzer              →  Pin 15
GPIO23_RLED = 23   # Red LED (ARMED)           →  Pin 16
GPIO24_GLED = 24   # Green LED (IDLE)          →  Pin 18
GPIO25_BTN  = 25   # Arm / Disarm button       →  Pin 22

# ─────────────────────────────────────────────────────────────
#  GY-9250 / MPU-9250  I2C SETUP
# ─────────────────────────────────────────────────────────────
I2C_BUS      = 1
MPU_ADDR     = 0x68    # AD0 pin wired to GND
ACCEL_XOUT_H = 0x3B    # First accelerometer register
PWR_MGMT_1   = 0x6B    # Power management register

# ─────────────────────────────────────────────────────────────

THRESHOLD = 0.8

# ─────────────────────────────────────────────────────────────
#  INITIALISE I2C BUS AND WAKE UP SENSOR
# ─────────────────────────────────────────────────────────────
bus = smbus2.SMBus(I2C_BUS)
bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)  # wake sensor from sleep

# ─────────────────────────────────────────────────────────────
#  MQTT SETUP
# ─────────────────────────────────────────────────────────────
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"MQTT Connected > {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"MQTT connection failed, code: {rc}")

mqtt_client.on_connect = on_connect
try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"  [MQTT] Could not connect: {e} — running without MQTT")

# ─────────────────────────────────────────────────────────────
#  CSV LOG FILE SETUP
# ─────────────────────────────────────────────────────────────
def init_log():
    """Create log file with header if it doesn't exist."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "time", "event", "cause",
                             "accel_g", "baseline", "deviation"])
        print(f"  [LOG] Created log file: {LOG_FILE}")
    else:
        print(f"  [LOG] Appending to existing log: {LOG_FILE}")

# ─────────────────────────────────────────────────────────────
#  SENSOR READING FUNCTIONS
# ─────────────────────────────────────────────────────────────
def read_accel():
    """Read 3-axis acceleration and return total magnitude."""
    raw = bus.read_i2c_block_data(MPU_ADDR, ACCEL_XOUT_H, 6)

    def to_signed16(high_byte, low_byte):
        value = (high_byte << 8) | low_byte
        return value - 65536 if value > 32767 else value

    ax = to_signed16(raw[0], raw[1]) / 16384.0   # convert to g
    ay = to_signed16(raw[2], raw[3]) / 16384.0
    az = to_signed16(raw[4], raw[5]) / 16384.0
    return math.sqrt(ax*ax + ay*ay + az*az)       # total magnitude


def calibrate(samples=30):
    """Sample the accelerometer at rest to establish a baseline."""
    print("  Calibrating — keep the unit still...")
    readings = []
    for _ in range(samples):
        readings.append(read_accel())
        time.sleep(0.05)
    baseline = sum(readings) / len(readings)
    print(f"  Calibration done. Baseline = {baseline:.4f} g")
    return baseline

# ─────────────────────────────────────────────────────────────
#  GPIO SETUP
# ─────────────────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO17_VIB,  GPIO.IN)
GPIO.setup(GPIO22_BUZ,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(GPIO23_RLED, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(GPIO24_GLED, GPIO.OUT, initial=GPIO.HIGH)   # green ON at startup
GPIO.setup(GPIO25_BTN,  GPIO.IN,  pull_up_down=GPIO.PUD_UP)

# ─────────────────────────────────────────────────────────────
#  STATE CONTROL FUNCTIONS
# ─────────────────────────────────────────────────────────────
def set_idle():
    """Green LED on, red LED off, buzzer off."""
    GPIO.output(GPIO24_GLED, GPIO.HIGH)
    GPIO.output(GPIO23_RLED, GPIO.LOW)
    GPIO.output(GPIO22_BUZ,  GPIO.LOW)


def set_armed():
    """Red LED on, green LED off."""
    GPIO.output(GPIO24_GLED, GPIO.LOW)
    GPIO.output(GPIO23_RLED, GPIO.HIGH)


def sound_alarm(duration=3):
    """Beep the buzzer using PWM for a given number of seconds."""
    pwm = GPIO.PWM(GPIO22_BUZ, 1000)
    pwm.start(50)
    time.sleep(duration)
    pwm.stop()
    GPIO.output(GPIO22_BUZ, GPIO.LOW)

# ─────────────────────────────────────────────────────────────
#  LOG EVENT — saves to CSV and publishes to MQTT
# ─────────────────────────────────────────────────────────────
def log_event(event, cause, accel, baseline_val):
    """Log event to CSV file and publish to MQTT broker."""
    date_str = time.strftime("%Y-%m-%d")
    time_str = time.strftime("%H:%M:%S")
    accel_r  = round(accel, 4)
    base_r   = round(baseline_val, 4)
    dev_r    = round(abs(accel - baseline_val), 4)

    # ── Save to CSV log file ──────────────────────────────────
    try:
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([date_str, time_str, event, cause,
                             accel_r, base_r, dev_r])
        print(f"  [LOG]  Saved → {event} | {cause} | dev={dev_r}")
    except Exception as e:
        print(f"  [LOG]  Error writing log: {e}")

    # ── Publish to MQTT (Node-RED → Telegram) ─────────────────
    payload = {
        "date":      date_str,
        "time":      time_str,
        "event":     event,
        "cause":     cause,
        "accel_g":   accel_r,
        "baseline":  base_r,
        "deviation": dev_r
    }
    try:
        mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
        print(f"  [MQTT] Published → {MQTT_TOPIC}")
    except Exception as e:
        print(f"  [MQTT] Publish error: {e}")

# ─────────────────────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────────────────────
init_log()

armed      = False
baseline   = None
last_press = 0

print("=" * 55)
print("  Bike Theft Detection System  —  READY")
print("  Press the button to ARM or DISARM")
print("=" * 55)
set_idle()

try:
    while True:

        # ── Button: toggle arm/disarm ─────────────────────────
        if GPIO.input(GPIO25_BTN) == GPIO.LOW and \
                time.time() - last_press > 0.5:       # debounce 500 ms

            last_press = time.time()
            armed = not armed

            if armed:
                baseline = calibrate()
                set_armed()
                log_event("ARMED", "Button", 0.0, 0.0)
                print(">>> SYSTEM ARMED  — monitoring for theft <<<")
            else:
                set_idle()
                log_event("DISARMED", "Button", 0.0, 0.0)
                print(">>> SYSTEM DISARMED  — standing by <<<")

        # ── Theft detection (only when armed) ─────────────────
        if armed:
            accel = read_accel()
            vib   = GPIO.input(GPIO17_VIB)

            motion_detected    = abs(accel - baseline) > THRESHOLD
            vibration_detected = (vib == GPIO.HIGH)

            if motion_detected or vibration_detected:
                timestamp = time.strftime("%H:%M:%S")
                cause     = "MOTION" if motion_detected else "VIBRATION"

                print(f"\n[{timestamp}] *** THEFT ALERT ***")
                print(f"  Cause     : {cause}")
                print(f"  Accel now : {accel:.4f} g")
                print(f"  Baseline  : {baseline:.4f} g")
                print(f"  Deviation : {abs(accel - baseline):.4f} g")
                print(f"  Vib pin   : {vib}")
                print()

                log_event("THEFT_ALERT", cause, accel, baseline)
                sound_alarm(duration=3)

                # Re-baseline after alarm (unit may be in new position)
                baseline = calibrate()

        time.sleep(0.05)   # 50 ms loop — responsive but not CPU-heavy

except KeyboardInterrupt:
    print("\nCtrl+C detected — shutting down cleanly.")

finally:
    try:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    except:
        pass
    GPIO.cleanup()
    print("GPIO cleaned up. Goodbye.")
    print(f"Event log saved to: {LOG_FILE}")
