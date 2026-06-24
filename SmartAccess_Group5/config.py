from pathlib import Path

# PubNub settings
PUBLISH_KEY = "pub-c-ae5f8ca3-617c-4d1d-9ef4-d5e599c6c010"
SUBSCRIBE_KEY = "sub-c-0ec174c8-16b1-46d1-8389-651b05629083"

ACCESS_CHANNEL = "769IoT_access"
REGISTER_CHANNEL = "769IoT_register"

SUBSCRIBE_CHANNELS = [
    ACCESS_CHANNEL,
    REGISTER_CHANNEL
]
PI_SOURCE = "pi"
WEB_SOURCE = "web"


# Local storage
AUTHORIZED_FILE = Path("authorized_cards.txt")
LOG_FILE = Path("access_log.csv")


# Timing
REGISTER_TIMEOUT_SECONDS = 10
COOLDOWN_SECONDS = 2


# Servo settings
SERVO_PIN = 40
CLOSE_ANGLE = 0
OPEN_ANGLE = 90


# LCD settings
LCD_ADDR = 0x27
LCD_WIDTH = 16


# LED settings
RED_LED_PIN = 36
GREEN_LED_PIN = 33
