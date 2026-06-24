import time
import RPi.GPIO as GPIO
from config import SERVO_PIN, CLOSE_ANGLE, OPEN_ANGLE


class DoorServo:
    def __init__(self):
        self.pwm = None

    def init(self):
        GPIO.setup(SERVO_PIN, GPIO.OUT)
        self.pwm = GPIO.PWM(SERVO_PIN, 50)
        self.pwm.start(0)
        self.set_angle(CLOSE_ANGLE)
        print("Servo initialized.")

    def set_angle(self, angle):
        if self.pwm is None:
            return
        duty = 2.5 + (angle / 18.0)
        self.pwm.ChangeDutyCycle(duty)
        time.sleep(0.7)
        self.pwm.ChangeDutyCycle(0)

    def unlock_then_lock(self):
        print("Servo: open door")
        self.set_angle(OPEN_ANGLE)
        time.sleep(2)
        print("Servo:close door")
        self.set_angle(CLOSE_ANGLE)

    def close(self):
        if self.pwm is not None:
            self.pwm.stop()
