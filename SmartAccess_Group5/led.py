import time
import RPi.GPIO as GPIO
from config import RED_LED_PIN, GREEN_LED_PIN


class AccessLED:
    def __init__(self):
        self.red_pin = RED_LED_PIN
        self.green_pin = GREEN_LED_PIN

    def init(self):
        GPIO.setup(self.red_pin, GPIO.OUT)
        GPIO.setup(self.green_pin, GPIO.OUT)
        self.off()
        print("LED initialized.")

    def off(self):
        GPIO.output(self.red_pin, GPIO.LOW)
        GPIO.output(self.green_pin, GPIO.LOW)

    def green_on(self):
        GPIO.output(self.red_pin, GPIO.LOW)
        GPIO.output(self.green_pin, GPIO.HIGH)

    def red_on(self):
        GPIO.output(self.green_pin, GPIO.LOW)
        GPIO.output(self.red_pin, GPIO.HIGH)

    def show_granted(self,seconds=2):
        self.green_on()
        time.sleep(seconds)
        self.off()

    def show_denied(self, seconds=2):
        self.red_on()
        time.sleep(seconds)
        self.off()
