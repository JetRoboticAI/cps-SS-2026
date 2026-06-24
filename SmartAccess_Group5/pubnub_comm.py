from datetime import datetime
from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub
from pubnub.callbacks import SubscribeCallback
from pubnub.enums import PNStatusCategory
from config import (
    PUBLISH_KEY,
    SUBSCRIBE_KEY,
    ACCESS_CHANNEL,
    REGISTER_CHANNEL,
    SUBSCRIBE_CHANNELS,
    PI_SOURCE,
    WEB_SOURCE
)

class IoTPubNub:
    def __init__(self, register_callback):
        self.register_callback = register_callback
        pnconfig = PNConfiguration()
        pnconfig.publish_key = PUBLISH_KEY
        pnconfig.subscribe_key = SUBSCRIBE_KEY
        pnconfig.ssl = True
        pnconfig.user_id = "access_control"
        self.pubnub = PubNub(pnconfig)

    def start_subscribe(self):
        listener = self._CommandListener(self.register_callback)
        self.pubnub.add_listener(listener)
        self.pubnub.subscribe().channels(SUBSCRIBE_CHANNELS).execute()
        print("subscribing to:", SUBSCRIBE_CHANNELS)

    def publish_access_event(self, event, card_id="", status="", door_action="none"):
        return self._publish_event(
            channel=ACCESS_CHANNEL,
            event=event,
            card_id=card_id,
            status=status,
            door_action=door_action,
            channel_type="access"
        )

    def publish_register_event(self, event, card_id="", status="", door_action="none"):
        return self._publish_event(
            channel=REGISTER_CHANNEL,
            event=event,
            card_id=card_id,
            status=status,
            door_action=door_action,
            channel_type="register"
        )

    def _publish_event(
        self,
        channel,
        event,
        card_id="",
        status="",
        door_action="none",
        channel_type=""
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = {
            "msg_type": "event",
            "source": PI_SOURCE,
            "channel_type": channel_type,
            "event": event,
            "card_id": str(card_id),
            "status": status,
            "door_action": door_action,
            "time": now
        }
        try:
            envelope = (
                self.pubnub.publish()
                .channel(channel)
                .message(message)
                .sync()
            )
            if envelope.status.is_error():
                print("publish failed:", envelope.status.category)
                return "pubnub_failed"
            print("event sent to", channel, ":", message)
            return "pubnub_sent"
        except Exception as e:
            print("error:", e)
            return "pubnub_failed"

    def stop(self):
        try:
            self.pubnub.unsubscribe_all()
            self.pubnub.stop()
        except Exception:
            pass

    class _CommandListener(SubscribeCallback):
        def __init__(self, register_callback):
            self.register_callback = register_callback

        def status(self, pubnub, status):
            if status.category == PNStatusCategory.PNConnectedCategory:
                print("connected.")
            elif status.is_error():
                print("subscribe error:",  status.category)

        def message(self, pubnub, message):
            payload = message.message
            incoming_channel = getattr(message, "channel", "")
            if not isinstance(payload, dict):
                return
            if payload.get("source") == PI_SOURCE:
                return
            if payload.get("msg_type") !=  "command":
                return
            if payload.get("source") != WEB_SOURCE:
                return
            command = payload.get("command")
            print("command received from", incoming_channel, ":", command)
            if command == "register_next_card":
                self.register_callback()
