# main_showroom.py
# Run this file on Raspberry Pi.
# Command: python3 main_showroom.py

import time
import sqlite3
import threading
from datetime import datetime
from flask import Flask
from dashboard_ui import render_dashboard

# -------------------------------------------------
# GPIO safe import
# -------------------------------------------------
try:
    import RPi.GPIO as GPIO
    PI_MODE = True
except ImportError:
    PI_MODE = False

    class MockGPIO:
        BCM = "BCM"
        OUT = "OUT"
        IN = "IN"
        HIGH = 1
        LOW = 0

        def setmode(self, mode): pass
        def setwarnings(self, flag): pass
        def setup(self, pin, mode): pass
        def output(self, pin, value): pass
        def input(self, pin): return 0
        def cleanup(self): pass

    GPIO = MockGPIO()

# -------------------------------------------------
# Pin configuration
# -------------------------------------------------
TRIG1 = 23
ECHO1 = 24
LED1 = 17
BUZZER1 = 18

TRIG2 = 5
ECHO2 = 6
LED2 = 27
BUZZER2 = 22

DIST_CM = 30
ANOMALY_SEC = 15.0
RECOMMEND_SEC = 17.0
GLITCH_FILTER = 5
DB_NAME = "showroom_logs.db"

app = Flask(__name__)
data_lock = threading.Lock()

latest_data = {
    "timestamp": "-",
    "dist1": "-",
    "dist2": "-",
    "dwell1": 0.0,
    "dwell2": 0.0,
    "score1": 0,
    "score2": 0,
    "led1": 0,
    "led2": 0,
    "buzzer1": 0,
    "buzzer2": 0,
    "status1": "Waiting",
    "status2": "Waiting",
    "system_status": "System Starting",
    "recommended_product": "No active recommendation",
    "recommendation_reason": "<li>Waiting for customer interaction</li>",
}

# -------------------------------------------------
# Database
# -------------------------------------------------
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sensor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                sensor1_distance TEXT,
                sensor2_distance TEXT,
                sensor1_dwell REAL,
                sensor2_dwell REAL,
                sensor1_score REAL,
                sensor2_score REAL,
                led1_status INTEGER,
                led2_status INTEGER,
                buzzer1_status INTEGER,
                buzzer2_status INTEGER,
                recommended_product TEXT,
                recommendation_reason TEXT,
                system_status TEXT
            )
        """)
        conn.commit()


def save_data(row):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sensor_logs (
                timestamp, sensor1_distance, sensor2_distance,
                sensor1_dwell, sensor2_dwell,
                sensor1_score, sensor2_score,
                led1_status, led2_status,
                buzzer1_status, buzzer2_status,
                recommended_product, recommendation_reason, system_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["timestamp"], str(row["dist1"]), str(row["dist2"]),
            row["dwell1"], row["dwell2"],
            row["score1"], row["score2"],
            row["led1"], row["led2"],
            row["buzzer1"], row["buzzer2"],
            row["recommended_product"], row["recommendation_reason"], row["system_status"]
        ))
        conn.commit()

# -------------------------------------------------
# GPIO setup
# -------------------------------------------------
def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    for pin in [TRIG1, TRIG2, LED1, LED2, BUZZER1, BUZZER2]:
        GPIO.setup(pin, GPIO.OUT)

    for pin in [ECHO1, ECHO2]:
        GPIO.setup(pin, GPIO.IN)

    for pin in [TRIG1, TRIG2, LED1, LED2, BUZZER1, BUZZER2]:
        GPIO.output(pin, GPIO.LOW)

    time.sleep(0.5)

# -------------------------------------------------
# Sensor functions
# -------------------------------------------------
def measure_distance(trig, echo):
    if not PI_MODE:
        return None

    GPIO.output(trig, GPIO.HIGH)
    time.sleep(0.00001)
    GPIO.output(trig, GPIO.LOW)

    timeout = time.time() + 0.04
    start = time.time()

    while GPIO.input(echo) == 0:
        start = time.time()
        if time.time() > timeout:
            return None

    stop = time.time()

    while GPIO.input(echo) == 1:
        stop = time.time()
        if time.time() > timeout:
            return None

    distance = (stop - start) * 34300 / 2
    return round(distance, 1)


def calculate_score(distance, dwell_time):
    if distance is None:
        return 0
    score = (min(dwell_time, ANOMALY_SEC) / ANOMALY_SEC) * 100
    return round(score, 1)


def get_dwell_status(dwell_time, detected):
    if not detected:
        return "No Detection"
    if dwell_time < 5:
        return "Browsing"
    if dwell_time < 12:
        return "Interested"
    if dwell_time < 15:
        return "Highly Interested"
    return "Engagement Alert"


def get_recommendation(score1, score2, dwell1, dwell2):
    if score1 >= 100 and dwell1 >= RECOMMEND_SEC and score1 >= score2:
        return "Vision Pro Accessory Kit", """
            <li>Vision Pro Travel Case</li>
            <li>Extra Battery Holder</li>
            <li>Light Seal Cushion</li>
            <li>Lens Cleaning Kit</li>
            <li>AirPods Pro / Spatial Audio Earbuds</li>
        """

    if score2 >= 100 and dwell2 >= RECOMMEND_SEC and score2 > score1:
        return "Apple Smart Ring Band Kit", """
            <li>Premium Ring Band</li>
            <li>Magnetic Charging Dock</li>
            <li>Ring Protector</li>
            <li>Travel Pouch</li>
            <li>Wellness / Fitness Sync Pack</li>
        """

    return "No active recommendation", "<li>Customer engagement is not high enough for recommendation yet.</li>"

# -------------------------------------------------
# Main sensor loop
# -------------------------------------------------
def sensor_loop():
    global latest_data

    dwell_start1 = None
    dwell_start2 = None
    none_count1 = 0
    none_count2 = 0

    while True:
        current_time = time.time()
        dist1 = measure_distance(TRIG1, ECHO1)
        dist2 = measure_distance(TRIG2, ECHO2)

        if dist1 is not None and dist1 < DIST_CM:
            none_count1 = 0
            GPIO.output(LED1, GPIO.HIGH)
            if dwell_start1 is None:
                dwell_start1 = current_time
            GPIO.output(BUZZER1, GPIO.HIGH if current_time - dwell_start1 >= ANOMALY_SEC else GPIO.LOW)
        else:
            none_count1 += 1
            if none_count1 >= GLITCH_FILTER:
                dwell_start1 = None
                GPIO.output(LED1, GPIO.LOW)
                GPIO.output(BUZZER1, GPIO.LOW)

        if dist2 is not None and dist2 < DIST_CM:
            none_count2 = 0
            GPIO.output(LED2, GPIO.HIGH)
            if dwell_start2 is None:
                dwell_start2 = current_time
            GPIO.output(BUZZER2, GPIO.HIGH if current_time - dwell_start2 >= ANOMALY_SEC else GPIO.LOW)
        else:
            none_count2 += 1
            if none_count2 >= GLITCH_FILTER:
                dwell_start2 = None
                GPIO.output(LED2, GPIO.LOW)
                GPIO.output(BUZZER2, GPIO.LOW)

        dwell1 = round(current_time - dwell_start1, 1) if dwell_start1 else 0.0
        dwell2 = round(current_time - dwell_start2, 1) if dwell_start2 else 0.0
        score1 = calculate_score(dist1, dwell1)
        score2 = calculate_score(dist2, dwell2)

        led1 = GPIO.input(LED1)
        led2 = GPIO.input(LED2)
        buzzer1 = GPIO.input(BUZZER1)
        buzzer2 = GPIO.input(BUZZER2)

        recommended_product, recommendation_reason = get_recommendation(score1, score2, dwell1, dwell2)

        system_status = "Monitoring"
        if buzzer1 or buzzer2:
            system_status = "High Engagement Alert"
        elif led1 or led2:
            system_status = "Live Engagement Tracking"

        row = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dist1": dist1 if dist1 is not None else "No Signal",
            "dist2": dist2 if dist2 is not None else "No Signal",
            "dwell1": dwell1,
            "dwell2": dwell2,
            "score1": score1,
            "score2": score2,
            "led1": led1,
            "led2": led2,
            "buzzer1": buzzer1,
            "buzzer2": buzzer2,
            "status1": get_dwell_status(dwell1, led1),
            "status2": get_dwell_status(dwell2, led2),
            "system_status": system_status,
            "recommended_product": recommended_product,
            "recommendation_reason": recommendation_reason,
        }

        with data_lock:
            latest_data = row

        save_data(row)

        print(f"S1: {row['dist1']} cm | Dwell: {dwell1}s | Score: {score1} | LED: {led1} | Buzzer: {buzzer1}")
        print(f"S2: {row['dist2']} cm | Dwell: {dwell2}s | Score: {score2} | LED: {led2} | Buzzer: {buzzer2}")
        print(f"Recommendation: {recommended_product}")
        print("-" * 60)

        time.sleep(0.15)

# -------------------------------------------------
# Flask route
# -------------------------------------------------
@app.route("/")
def dashboard():
    with data_lock:
        page_data = latest_data.copy()
    return render_dashboard(page_data)

# -------------------------------------------------
# Start app
# -------------------------------------------------
if __name__ == "__main__":
    init_db()
    setup_gpio()

    thread = threading.Thread(target=sensor_loop, daemon=True)
    thread.start()

    try:
        app.run(host="0.0.0.0", port=5000, debug=False)
    finally:
        GPIO.cleanup()
        print("GPIO cleaned up. System stopped.")
