import threading

from gpiozero import Device,LED, AngularServo, Button
from gpiozero.pins.pigpio import PiGPIOFactory

import time
import cv2
import json
import paho.mqtt.client as mqtt

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import base64

Device.pin_factory = PiGPIOFactory()


class SmartBox:
    def __init__(self) -> None:
        #Hardware Setup
        self.ledRed = LED(17)
        self.ledGreen = LED(27)
        self.servo = AngularServo(18, min_pulse_width=0.0006,max_pulse_width=0.0023)

        self.button = Button(5,bounce_time=0.1)
        self.button.when_pressed = self.handleButton

        #Data Config and init
        self.captureTime = 5 # 5 Seconds
        self.captureTill = time.time()
        self.frameCounter = 0
        self.sessionID = 0
        self.frameID = 0
        self.lastData = True

        self.isOpen = False

        self.setupCamera()
        self.loadKeys()

        #MQTT Setup
        self.broker = "LAPTOP-RFNGTH6N.local"
        self.port = 1883
        self.username = "SafeLockBox"
        self.password = "SafePass1"

        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(self.username, self.password)
        # self.client.tls_set()

        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect      
        self.client.connect(self.broker, self.port)


        self.imageTopic = "lockbox/image"
        self.client.subscribe("lockbox/results")
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reasonCode, properties=None):
        '''This Function is Run during MQTT Connection'''
        print("Connected:", reasonCode)

    def on_disconnect(self, client, userdata, flags, reasonCode, properties=None):
        '''This Function is Run during MQTT Disconnection'''
        print("Disonnected:", reasonCode)

    def loadKeys(self):
        '''Loads the Public and Private Encrpytion keys for signaturing and verification'''

        #Load Client Private Key
        with open(r"keys/client_private_key.bin", "rb") as f:
            self.privateKey = Ed25519PrivateKey.from_private_bytes(f.read())

        #Load the Client Public Key
        with open(r"keys/client_public_key.bin", "rb") as f:
            self.publicKey = Ed25519PublicKey.from_public_bytes(f.read())

        #Load the Server Public Key
        with open(r"keys/server_public_key.bin", "rb") as f:
            self.serverPublicKey = Ed25519PublicKey.from_public_bytes(f.read())

    def on_message(self, client, userdata, msg):
        '''This function is called everytime a message is received from MQTT'''
        try:
            # Check if topic of the message is the correct topic
            if msg.topic == "lockbox/results":
                # Convert Data into JSON (Dictionary)
                rawData = json.loads(msg.payload)
                signature = rawData['signature']
                jsonData = rawData['payload']
                try:
                    # Check if Signature Matches else it might be a spoofing attempt
                    jsonEnc = json.dumps(jsonData, sort_keys=True).encode("utf-8")
                    self.serverPublicKey.verify(base64.b64decode(signature), jsonEnc)
                except InvalidSignature:
                    print("Possible Spoofing Attempt!!!")
                    return
                print(jsonData)
                # If user is an authorized person then open the box else reject the attempt
                if jsonData['valid'] == True:
                    self.openLock()
                else:
                    self.rejectCheck()
        except Exception:
            print("Exception Occured in Message read")
            return

    def send_frame(self,frame,sessionID:int,frameID:int,timestamp:float,lastData=False):
        '''
        Send the image and its metadata to the server
        Params:
            frame(cv2.typing.MatLike): Image Frame to be sent
            sessionID(int): ID of the Session
            frameID(int): ID of the Frame
            timestamp(float): Current Timestamp
            lastData(bool): Whether the data is last of the sequence, (default: False)
        
        '''
        #Convert image into byte buffer
        _, buffer = cv2.imencode('.jpg', frame, [
            int(cv2.IMWRITE_JPEG_QUALITY), 60
        ])
        imgbytes = buffer.tobytes()

        # Add image Metadata to the mesaage  
        jsonData  = {"Image":base64.b64encode(imgbytes).decode(),
                     "CurrentlyOpen": self.isOpen,
                     "SessionID": sessionID,
                     "FrameID": frameID,
                     "TimeStamp":timestamp,
                     "LastData":lastData}
        data = json.dumps(jsonData, sort_keys=True).encode("utf-8")

        #Sign the image to prevent tampering
        signature = self.privateKey.sign(data)
        message = {
        "payload": jsonData,
        "signature": base64.b64encode(signature).decode("utf-8")
        }

        #Publish the message to topic
        self.client.publish(self.imageTopic,json.dumps(message),qos=1)


    def setupCamera(self):
        '''Sets up the camera'''
        self.cap = cv2.VideoCapture(0,cv2.CAP_V4L2)

    def captureImage(self):
        '''Reads the frame from camera and reduces the resolution'''
        ret, frame = self.cap.read()
        if not ret:
            print("No Frame")
        frame = cv2.resize(frame, (640, 480))
        return frame

    def handleButton(self):
        '''Handles what action to perform after button push'''
        if not self.isOpen:
            self.captureTill=time.time()+self.captureTime
            self.frameCounter = 0
            self.frameID = 0
            self.sessionID+=1
        else:
            self.resetState()


    def openLock(self):
        '''Open the Lock and Turn The Green LED On'''
        self.ledGreen.on()
        self.servo.angle = 90
        self.isOpen = True

    def rejectCheck(self):
        '''Reject The access attempt and Turn the RED LED on'''
        self.ledRed.on()
        self.isOpen = False
        time.sleep(2)
        self.ledRed.off()

    def resetState(self):
        '''Reset the State of the box'''
        self.ledGreen.off()
        self.ledRed.off()
        if self.isOpen:
            while self.servo.angle > 0:
                self.servo.angle -= 5
                time.sleep(0.1)
        self.servo.angle = 0
        self.frameCounter = 0
        self.isOpen = False

    def mainLoop(self):
        '''The Main Program Loop of The Client'''
        #capture one frame to avoid None Errors
        frame = self.captureImage()

        #Perform the Following loop as long as program is active
        while True:
            #if Time is withing capture window take the image and send every 5th image to server
            if time.time()<=self.captureTill:
                self.lastData=False
                frame = self.captureImage()
                cv2.imshow("Img",frame)
                if self.frameCounter % 5 == 0:
                    self.send_frame(frame,self.sessionID,self.frameID,time.time(),False)
                    self.frameID+=1         
                self.frameCounter+=1

            #if window is completed send a termination message to the server
            elif not self.lastData:
                self.send_frame(frame,self.sessionID,self.frameID,time.time(),True)
                self.lastData = True

            #waitkey for opencv imshow window and program exit condition
            if cv2.waitKey(1) == ord('q'):
                break

        # Close all processes if program is stopped
        cv2.destroyAllWindows()
        self.cap.release()
        self.client.loop_stop()

#Main Code That act as entrypoint
if __name__ == "__main__":
    Box = SmartBox()
    Box.mainLoop()