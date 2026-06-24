from mfrc522 import SimpleMFRC522

class RFIDReader:
    def __init__(self):
        self.reader = None

    def init(self):
        self.reader = SimpleMFRC522()
        print("RFID reader initialized.")

    def read_card_id(self):
        if self.reader is None:
            return None
        card_id = self.reader.read_id_no_block()
        if card_id:
            return str(card_id)
        return None
