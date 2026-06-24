from SmartLockBox_Group9.FacialRec.app import FaceResult,Match,analyze_faces,create_engine,create_spoof_detector,FaceDatabase
from SmartLockBox_Group9.FacialRec.config import load_config

import cv2
import paho.mqtt.client as mqtt
import numpy as np
from pathlib import Path
import json
import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

import sqlite3 as sql
import uuid

class SmartBox:
    def __init__(self) -> None:
        # Face Recognition Setup
        config_path:Path = Path(r"config.json")
        self.config = load_config(config_path)
        self.engine = create_engine(self.config)
        self.database = FaceDatabase(self.config.model_pack.database)
        self.spoof_detector = create_spoof_detector(self.config)

        # Loading Encryption Keys
        self.loadKeys()

        # SQL Setup
        self.sqlConnect()
        self.createTable()

        #Data Setup
        self.frame = None
        self.currentSessionID: int = 0
        self.currentFrameID: int = 0
        self.lastData = False
        self.resultGroup: dict[str,tuple[int,float]] = {}
        self.simThreshold = 0.5
        self.logID = uuid.uuid4()
        self.sessionCommandDone = False

        #MQTT Setup
        self.broker = "LAPTOP-AB74TNG.local"
        self.port = 1883
        self.username = "LockBoxServer"
        self.password = "SafePass1"

        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(self.username, self.password)
        # self.client.tls_set()

        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect 
        self.client.connect(self.broker, self.port)


        self.resultTopic = "lockbox/results"
        self.client.subscribe("lockbox/image")
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reasonCode, properties=None):
        '''This Function is Run during MQTT Connection'''
        print("Connected:", reasonCode)

    def on_disconnect(self, client, userdata, flags, reasonCode, properties=None):
        '''This Function is Run during MQTT Disconnection'''
        print("Disonnected:", reasonCode)

    def on_message(self, client, userdata, msg):
        '''This function is called everytime a message is received from MQTT'''
        # check if message topic is the image topic
        if msg.topic == "lockbox/image":
            #load and split the data
            rawData = json.loads(msg.payload)
            signature = rawData['signature']
            jsonData = rawData['payload']
            try:
                # Check if signature is valid
                jsonEnc = json.dumps(jsonData, sort_keys=True).encode("utf-8")
                self.clientPublicKey.verify(base64.b64decode(signature), jsonEnc)
            except InvalidSignature:
                print("Possible Spoofing Attempt!!!")
                return

            #Split the Data into seperate variables
            np_arr = np.frombuffer(base64.b64decode(jsonData['Image']), np.uint8)
            self.frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            self.frameID = jsonData['FrameID']
            self.sessionID = jsonData['SessionID']
            self.lastData = jsonData['LastData']
            self.isOpen = jsonData['CurrentlyOpen']
            self.timestamp = jsonData['TimeStamp']
   
    def loadKeys(self):
        '''Loads the Public and Private Encrpytion keys for signaturing and verification'''
        with open(r"keys\server_private_key.bin", "rb") as f:
            self.privateKey = Ed25519PrivateKey.from_private_bytes(f.read())

        with open(r"keys\server_public_key.bin", "rb") as f:
            self.publicKey = Ed25519PublicKey.from_public_bytes(f.read())

        with open(r"keys\client_public_key.bin", "rb") as f:
            self.clientPublicKey = Ed25519PublicKey.from_public_bytes(f.read())

    def sqlConnect(self):
        '''Connects with the Local SQLite database'''
        self.conn = sql.connect("lockbox.db")
        self.cursor = self.conn.cursor()

    def createTable(self):
        '''Create a table to store the access logs'''
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS Logs (
            uuid TEXT PRIMARY KEY,
            session_id INTEGER,
            timestamp INTEGER,
            user TEXT,
            similarity REAL,
            lock_open BOOL,
            frame_count INTEGER,
            image_path TEXT
        )
        """)

        self.conn.commit()

    def addTableDate(self,user, sim):
        '''Add Data to the table
        Params:
            user(str): Name of the User
            sim(float): Similarity of the User
        Returns:
            None
        '''
        self.cursor.execute("""
        INSERT INTO Logs (
            uuid,
            session_id,
            timestamp,
            user,
            similarity,
            lock_open,
            frame_count,
            image_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(self.logID),
            self.currentSessionID,
            self.timestamp,
            user,
            sim,
            self.isOpen ,
            self.frameID,
            self.imageFolderPath
        ))
        self.conn.commit()



    def commandOpen(self, valid, user, similarity) -> None:
        '''Command the Client to open or close the box
        Params:
            valid(bool): Whether user is a valid user 
            user(str): Name of the Recognized User
            similarity(float): Simlarity score of the User
        Returns:
            None
        '''
        if self.sessionCommandDone:
            return
        jsonData  = {"valid":valid,"user": user, "similarity": similarity}
        print(jsonData)
        data = json.dumps(jsonData, sort_keys=True).encode("utf-8")
        signature = self.privateKey.sign(data)
        message = {
        "payload": jsonData,
        "signature": base64.b64encode(signature).decode("utf-8")
        }
        self.client.publish(self.resultTopic,json.dumps(message),qos=1)
        self.addTableDate(user,similarity)
        self.frame = None
        self.sessionCommandDone = True

    def addImage(self, imgFolder:str, frameID, frame):
        '''Adds image to the folder
        Params:
            imgFolder(str): Path to the Image Folder
            frameID(int): ID of the Image Frame
            frame(np.array): Image Frame
        Returns:
            None
        '''
        imageFolder = Path(imgFolder)
        imageFolder.mkdir(parents=True, exist_ok=True)
        imagePath = imageFolder/f"Session{self.currentSessionID}_frame{frameID}.jpg"
        cv2.imwrite(str(imagePath),frame)

    def checkSessionReset(self):
        '''Check if the current Data is from the same session or different session'''
        if self.currentSessionID != self.sessionID:
            self.logID = uuid.uuid4()
            self.imageFolderPath = rf"image/{str(self.logID)}"
            self.currentSessionID = self.sessionID
            self.currentFrameID = self.frameID
            self.resultGroup = {}
            self.sessionCommandDone = False

    def matchAggregation(self,match:Match):
        '''Aggregate the matches and open the box if past a threshold'''
        if self.frameID <= self.currentFrameID and len(self.resultGroup) !=0:
            return

        self.currentFrameID = self.frameID
        name, similarity = match.name,match.similarity
        self.addImage(self.imageFolderPath,self.currentFrameID,self.frame)
        if similarity > self.simThreshold:
            if name not in self.resultGroup:
                self.resultGroup[name] = (1,similarity)
            else:
                oldCount,oldSim = self.resultGroup[name]
                self.resultGroup[name] = (oldCount+1,oldSim+similarity)

        for name,data in self.resultGroup.items():
            avgSim = data[1]/data[0]
            if data[0]>5 and  avgSim> self.simThreshold and not self.isOpen:
                self.commandOpen(True, name,avgSim) 

        
    def performComparisons(self):
        '''Analyze the frame for faces, and if present compare if it matches the frame in Database'''
        if self.frame is not None:
            self.checkSessionReset()
        
            cv2.imshow("frame",self.frame)
            results:list[FaceResult] = analyze_faces(self.frame,self.engine,
                                                     self.database,self.spoof_detector,
                                                    self.config.recognition_threshold,)
            
            for result in results:
                if result.match is not None:
                    self.matchAggregation(result.match)
            self.frame = None
        elif self.lastData:
            if not self.isOpen:
                self.commandOpen(False,None,None)
            return

    def mainLoop(self):
        '''Main Program Loop of the Server'''
        while True:
            self.performComparisons()
            if cv2.waitKey(1) == ord('q'):
                break

        cv2.destroyAllWindows()

if __name__ == "__main__":
    BoxServer = SmartBox()
    BoxServer.mainLoop()