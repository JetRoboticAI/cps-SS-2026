import csv
from datetime import datetime
from config import AUTHORIZED_FILE, LOG_FILE


def init_files():
    if not AUTHORIZED_FILE.exists():
        AUTHORIZED_FILE.write_text("", encoding="utf-8")
    if not LOG_FILE.exists():
        with open(LOG_FILE, mode="w",newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "time",
                "card_id",
                "event",
                "status",
                "door_action",
                "pubnub_status"
            ])

def load_authorized_cards():
    if not AUTHORIZED_FILE.exists():
        return set()
    lines = AUTHORIZED_FILE.read_text(encoding="utf-8").splitlines()
    return set(line.strip() for line in lines if line.strip())


def add_authorized_card(card_id):
    card_id = str(card_id).strip()
    cards = load_authorized_cards()
    if card_id in cards:
        return False
    with open(AUTHORIZED_FILE, mode="a",encoding="utf-8") as file:
        file.write(card_id + "\n")
    return True


def write_access_log(card_id, event, status, door_action, pubnub_status):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            now,
            str(card_id),
            event,
            status,
            door_action,
            pubnub_status
        ])
