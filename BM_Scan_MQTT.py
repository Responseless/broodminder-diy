#!/usr/bin/python3

## Broodminder scanner and data logging based on https://github.com/dstrickler/broodminder-diy

from bluepy.btle import Scanner, DefaultDelegate
import time
import json
import sqlite3
from datetime import datetime
import paho.mqtt
import paho.mqtt.client as mqtt
from dotenv import dotenv_values

config = dotenv_values(".env")  # take environment variables

# MQTT settings (put in .env. See .env.example)
mq_broker_ip = config["mq_broker_ip"]
mq_port = int(config["mq_port"])
mq_topic_prefix = config["mq_topic_prefix"]
mq_username = config["mq_username"]
mq_password = config["mq_password"]

# Local SQLite Queue settings
DB_NAME = "offline_queue.db"

def init_db():
    """Initializes the local SQLite database for offline message queueing."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            payload TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the queue database on startup
init_db()


def save_to_local_queue(deviceId, json_data):
    """Saves a failed message to the local SQLite queue."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pending_messages (device_id, payload) VALUES (?, ?)", (deviceId, json_data))
        conn.commit()
        conn.close()
        print("  [Offline Storage] Message saved locally due to transmission failure.")
    except Exception as e:
        print(f"  [Error] Failed to save message locally: {e}")


def flush_local_queue(mqttc, topic_prefix):
    """Retransmits all locally stored offline messages when connection is restored."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, device_id, payload FROM pending_messages ORDER BY id ASC")
        rows = cursor.fetchall()
        
        if rows:
            print(f"  [Offline Queue] Attempting to retransmit {len(rows)} pending offline message(s)...")
            for row_id, device_id, payload in rows:
                try:
                    msg_info = mqttc.publish(topic_prefix + "/" + device_id + "/infojson", payload, qos=2, retain=True)
                    msg_info.wait_for_publish(timeout=5.0)
                    
                    # Remove from queue once successfully published
                    cursor.execute("DELETE FROM pending_messages WHERE id = ?", (row_id,))
                    conn.commit()
                    print(f"  [Offline Queue] Successfully retransmitted queued message ID {row_id}")
                except Exception as e:
                    print(f"  [Offline Queue] Retransmission interrupted for ID {row_id}: {e}")
                    break  # Stop flushing if network drops again
        conn.close()
    except Exception as e:
        print(f"  [Error] Error flushing local queue: {e}")


def SendToMQTT(deviceId, json_data):

    def on_publish(client, userdata, mid, reason_code=None, properties=None):
        try:
            userdata.remove(mid)
        except KeyError:
            pass

    unacked_publish = set()

    if not paho.mqtt.__version__.startswith("1."):
        mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqttc.on_publish = on_publish
    else:
        mqttc = mqtt.Client()
        mqttc.on_publish = on_publish

    mqttc.username_pw_set(username=mq_username, password=mq_password)
    mqttc.user_data_set(unacked_publish)

    try:
        print("Connecting to MQTT Broker")
        mqttc.connect(mq_broker_ip, mq_port, 60)
        mqttc.loop_start()
        print("MQTT Loop Start")

        # 1. Flush any old offline messages first
        flush_local_queue(mqttc, mq_topic_prefix)

        # 2. Publish current message
        msg_info = mqttc.publish(mq_topic_prefix + "/" + deviceId + "/infojson", json_data, qos=2, retain=True)
        unacked_publish.add(msg_info.mid)

        msg_info.wait_for_publish(timeout=5.0)

        mqttc.disconnect()
        mqttc.loop_stop()
        print("MQTT transmission successful.")

    except Exception as e:
        print(f"  [MQTT Error] Connection or publishing failed: {e}")
        save_to_local_queue(deviceId, json_data)
        try:
            mqttc.loop_stop()
        except:
            pass


def byte(str, byteNum):
    if (str == None):
        return ''
    return str[byteNum * 2] + str[byteNum * 2 + 1]


def checkBM(data):
    check = False
    byteCheck = 0
    BMIFLLC = str("8d02")
    if (BMIFLLC == byte(data, byteCheck) + byte(data, byteCheck + 1)):
        print("  Found BroodMinder device")
        check = True
    return check


def extractData(deviceId, data):

    offset = 8  # There are 8 bits less than described in BroodMinder documentation
    lbtokg = 0.45359237  # lb to kg

    byteNumAdvdeviceModelIFllc_1 = 10 - offset
    byteNumAdvDeviceVersionMinor_1 = 11 - offset
    byteNumAdvDeviceVersionMajor_1 = 12 - offset
    byteNumAdvBattery_1V2 = 14 - offset
    byteNumAdvElapsed_2 = 15 - offset   # This is the sample number from the device.
    byteNumAdvElapsed_2b = 16 - offset
    byteNumAdvTemperature_2 = 17 - offset
    byteNumAdvTemperature_2b = 18 - offset
    byteNumAdvWeightL1 = 20 - offset
    byteNumAdvWeightL2 = 21 - offset
    byteNumAdvWeightR1 = 22 - offset
    byteNumAdvWeightR2 = 23 - offset
    byteNumAdvHumidity = 24 - offset
    byteNumAdvWeightL2SM_Time0 = 25 - offset
    byteNumAdvWeightL2SM_Time1 = 26 - offset
    byteNumAdvWeightR2SM_Time2 = 27 - offset
    byteNumAdvWeightR2SM_Time3 = 28 - offset
    byteNumAdvRealtimeTotalWeight_SwarmState = 29 - offset
    byteNumAdvRealtimeTotalWeight = 30 - offset

    sampleNumber = int(byte(data, byteNumAdvElapsed_2b), 16) + int(byte(data, byteNumAdvElapsed_2), 16)
    modelNumber = int(byte(data, byteNumAdvdeviceModelIFllc_1), 16)
    versionNumber = str(int(byte(data, byteNumAdvDeviceVersionMajor_1), 16)) + "." + str(int(byte(data, byteNumAdvDeviceVersionMinor_1), 16))

    print("  Model Number = {}, Version = {}, Sample = {}".format(modelNumber, versionNumber, sampleNumber))

    realTimeWeight_lb = 0
    realTimeWeight_kg = 0

    if modelNumber == 49 or modelNumber == 57 or modelNumber == 58:
        weightR = (int(byte(data, byteNumAdvWeightL2), 16) * 256 + int(byte(data, byteNumAdvWeightL1), 16)) - 32767
        weightScaledR_lb = float(weightR / 100)
        weightScaledR_kg = weightScaledR_lb * lbtokg
        weightL = (int(byte(data, byteNumAdvWeightR2), 16) * 256 + int(byte(data, byteNumAdvWeightR1), 16)) - 32767
        weightScaledL_lb = float(weightL / 100)
        weightScaledL_kg = weightScaledL_lb * lbtokg

        weightR2 = (int(byte(data, byteNumAdvWeightL2SM_Time1), 16) * 256 + int(byte(data, byteNumAdvWeightL2SM_Time0), 16)) - 32767
        weightScaledR2_lb = float(weightR2 / 100)
        weightScaledR2_kg = weightScaledR2_lb * lbtokg
        weightL2 = (int(byte(data, byteNumAdvWeightR2SM_Time3), 16) * 256 + int(byte(data, byteNumAdvWeightR2SM_Time2), 16)) - 32767
        weightScaledL2_lb = float(weightL2 / 100)
        weightScaledL2_kg = weightScaledL2_lb * lbtokg

        realTimeWeight_lb = ((int(byte(data, byteNumAdvRealtimeTotalWeight), 16) * 256 + int(byte(data, byteNumAdvRealtimeTotalWeight_SwarmState), 16) - 32767 ) / 100)
        realTimeWeight_kg = round(realTimeWeight_lb * lbtokg, 2)
        realTimeWeight_lb = round(realTimeWeight_lb, 2)

    batteryPercent = int(byte(data, byteNumAdvBattery_1V2), 16)

    temperatureDegreesC = int(byte(data, byteNumAdvTemperature_2b) + byte(data, byteNumAdvTemperature_2), 16)
    temperatureDegreesC = (float(temperatureDegreesC) - 5000) / 100
    temperatureDegreesF = round((temperatureDegreesC * 9 / 5) + 32, 2)
    temperatureDegreesC = round(temperatureDegreesC, 2)

    if modelNumber == 41 or modelNumber == 47 or modelNumber == 49 or modelNumber == 52:
        humidityPercent = 0
    else:
        humidityPercent = int(byte(data, byteNumAdvHumidity))

    # Generate an ISO timestamp for when this reading was scanned
    current_timestamp = datetime.now().isoformat()

    data = {"timestamp": current_timestamp,
            "sampleNumber": sampleNumber,
            "modelNumber": modelNumber,
            "versionNumber": versionNumber,
            "batteryPercent": batteryPercent,
            "realTimeWeight_lb": realTimeWeight_lb,
            "realTimeWeight_kg": realTimeWeight_kg,
            "temperatureDegreesC": temperatureDegreesC,
            "temperatureDegreesF": temperatureDegreesF,
            "humidityPercent": humidityPercent
            }

    json_data = json.dumps(data)
    SendToMQTT(deviceId, json_data)


def processData(pdev):
    if (checkBM(pdev.getValueText(255))):
        print("  Device {} ({}), RSSI={} dB".format(pdev.addr, pdev.addrType, pdev.rssi))
        for (adtype, desc, value) in pdev.getScanData():
            print("    %s = %s" % (desc, value))

            if (desc == "Complete Local Name"):
                extractData(value, pdev.getValueText(255))

            extractData(value, pdev.getValueText(255))


class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            processData(dev)
        elif isNewData:
            processData(dev)

scanner = Scanner().withDelegate(ScanDelegate())
devices = scanner.scan(30.0)
