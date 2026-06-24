import time
import threading
import RPi.GPIO as GPIO
from config import (
    COOLDOWN_SECONDS,
    REGISTER_TIMEOUT_SECONDS
)
from storage import (
    init_files,
    load_authorized_cards,
    add_authorized_card,
    write_access_log
)
from lcd import LCDDisplay
from servo import DoorServo
from rfid import RFIDReader
from pubnub_comm import IoTPubNub
from led import AccessLED


class AccessControlSystem:
    def __init__(self):
        self.mode = "access"
        self.register_deadline = 0
        self.state_lock = threading.Lock()
        self.last_card_id = None
        self.last_scan_time = 0
        self.lcd = LCDDisplay()
        self.servo = DoorServo()
        self.rfid = RFIDReader()
        self.led = AccessLED()
        self.pubnub = IoTPubNub(self.enter_register_mode)

    def init(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        init_files()
        self.lcd.init()
        self.servo.init()
        self.led.init()
        self.rfid.init()
        self.pubnub.start_subscribe()
        self.lcd.display("Access Mode", "Scan card")
        self.led.off()
        print("System started.")
        print("Default mode: access")
        print("Press Ctrl+C to stop.\n")

    def enter_register_mode(self):
        with self.state_lock:
            self.mode = "register"
            self.register_deadline = time.time() +REGISTER_TIMEOUT_SECONDS
            self.last_card_id = None
            self.last_scan_time = 0

        print("Register mode enabled.")
        self.lcd.display("Registering", "Scan card")
        self.led.off()
        self.pubnub.publish_register_event(
            event="register_mode_started",
            status="Waiting for next card",
            door_action="none"
        )

    def check_register_timeout(self):
        with self.state_lock:
            is_timeout = (
                self.mode == "register"
                and time.time() > self.register_deadline
            )
            if not is_timeout:
                return
            self.mode = "access"
            self.register_deadline = 0
        print("Register mode timeout.")
        self.lcd.display("Register Timeout", "Back to access" )
        self.led.off()
        self.pubnub.publish_register_event(
            event="register_timeout",
            status="No card scanned",
            door_action="none"
        )
        time.sleep(1)
        self.lcd.display("Access Mode",  "Scan card")

    def process_card(self, card_id):
        card_id = str(card_id).strip()
        current_time = time.time()
        if (
            card_id == self.last_card_id
            and (current_time - self.last_scan_time) < COOLDOWN_SECONDS
        ):
            return
        self.last_card_id = card_id
        self.last_scan_time = current_time
        with self.state_lock:
            current_mode = self.mode
        print("Card detected:", card_id)
        print("Current mode:", current_mode)
        if current_mode == "register":
            self.handle_register_card(card_id)
        else:
            self.handle_access_card(card_id)
    def handle_register_card(self, card_id ):
        self.lcd.display("Registering", card_id[-8:])
        self.led.off()
        added = add_authorized_card(card_id)
        if added:
            print("Card registered:", card_id)
            self.lcd.display("Registered", card_id[-8:])
            pubnub_status = self.pubnub.publish_register_event(
                event="card_registered",
                card_id=card_id,
                status="Card Registered",
                door_action="none"
            )
            write_access_log(
                card_id=card_id,
                event="card_registered",
                status="Card Registered",
                door_action="none",
                pubnub_status=pubnub_status
            )

        else:
            print("Card already registered:", card_id)
            self.lcd.display("Already Exists", card_id[-8: ])
            pubnub_status = self.pubnub.publish_register_event(
                event="card_already_registered",
                card_id=card_id,
                status="Already Registered",
                door_action="none"
            )
            write_access_log(
                card_id=card_id,
                event="card_already_registered",
                status="Already Registered",
                door_action="none",
                pubnub_status=pubnub_status
            )

        with self.state_lock:
            self.mode = "access"
            self.register_deadline = 0

        time.sleep(1.5)
        self.led.off()
        self.lcd.display("Access Mode", "Scan card")

    def handle_access_card(self, card_id):
        authorized_cards = load_authorized_cards()
        if card_id in authorized_cards:
            print("Access Granted:", card_id)
            self.lcd.display("Door Open", card_id[-8:])
            self.led.green_on()
            self.servo.unlock_then_lock()
            self.led.off()
            pubnub_status = self.pubnub.publish_access_event(
                event="rfid_scan",
                card_id=card_id,
                status="Access Granted",
                door_action="unlocked"
            )
            write_access_log(
                card_id=card_id,
                event="rfid_scan",
                status="Access Granted",
                door_action="unlocked",
                pubnub_status=pubnub_status
            )

        else:
            print("Access Denied:", card_id)
            self.lcd.display("Unauthorized", card_id[-8:])
            self.led.show_denied(seconds=2)
            pubnub_status = self.pubnub.publish_access_event(
                event="rfid_scan",
                card_id=card_id,
                status="Access Denied",
                door_action="locked"
            )
            write_access_log(
                card_id=card_id,
                event="rfid_scan",
                status="Access Denied",
                door_action="locked",
                pubnub_status=pubnub_status
            )
        time.sleep(1)
        self.led.off()
        self.lcd.display("Access Mode", "Scan card")

    def run(self):
        self.init()
        try:
            while True:
                self.check_register_timeout()
                card_id = self.rfid.read_card_id()
                if card_id:
                    self.process_card(card_id)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nProgram stopped.")
        finally:
            self.cleanup()

    def cleanup(self):
        self.pubnub.stop()
        self.servo.close()
        self.lcd.close()
        self.led.off()
        GPIO.cleanup()
        print("GPIO cleaned up.")


if __name__ == "__main__":
    system = AccessControlSystem()
    system.run()
