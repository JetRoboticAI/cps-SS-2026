import time
from smbus2 import SMBus
from config import LCD_ADDR, LCD_WIDTH

LCD_CHR = 1
LCD_CMD = 0
LCD_LINE_1 = 0x80
LCD_LINE_2 = 0xC0
ENABLE = 0b00000100
BACKLIGHT = 0x08

class LCDDisplay:
    def __init__(self):
        self.bus = None

    def init(self):
        try:
            self.bus = SMBus(1)
            self._lcd_byte(0x33, LCD_CMD)
            self._lcd_byte(0x32, LCD_CMD)
            self._lcd_byte(0x06, LCD_CMD)
            self._lcd_byte(0x0C, LCD_CMD)
            self._lcd_byte(0x28, LCD_CMD)
            self._lcd_byte(0x01, LCD_CMD)
            time.sleep(0.005)
            self.display("769IoT", "System Ready")
            print("LCD initialized.")

        except Exception as e:
            print("LCD init failed:", e)
            self.bus = None

    def _toggle_enable(self, bits):
        if self.bus is None:
            return

        time.sleep(0.0005)
        self.bus.write_byte(LCD_ADDR, bits | ENABLE)
        time.sleep(0.0005)
        self.bus.write_byte(LCD_ADDR, bits & ~ENABLE)
        time.sleep(0.0005)

    def _lcd_byte(self, bits, mode):
        if self.bus is None:
            return

        high_bits = mode | (bits & 0xF0) | BACKLIGHT
        low_bits = mode | ((bits << 4) & 0xF0) | BACKLIGHT
        self.bus.write_byte(LCD_ADDR,  high_bits)
        self._toggle_enable(high_bits)
        self.bus.write_byte(LCD_ADDR, low_bits)
        self._toggle_enable(low_bits)

    def _lcd_string(self, message, line):
        if self.bus is None:
            return

        message = str(message)[:LCD_WIDTH].ljust(LCD_WIDTH, " ")
        self._lcd_byte(line, LCD_CMD)

        for char in message:
            self._lcd_byte(ord(char),LCD_CHR)

    def display(self, line1, line2=""):
        try:
            self._lcd_string(line1, LCD_LINE_1)
            self._lcd_string(line2, LCD_LINE_2)
        except Exception as e:
            print("LCD display failed:", e)

    def clear(self):
        try:
            self._lcd_byte(0x01, LCD_CMD)
        except Exception:
            pass

    def close(self):
        self.clear()
        if self.bus is not None:
            self.bus.close()
