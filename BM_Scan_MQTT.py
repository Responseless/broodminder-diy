#!/usr/bin/python3

## Broodminder scanner and data logging based on https://github.com/dstrickler/broodminder-diy

from bluepy.btle import Scanner, DefaultDelegate
import time
import json
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


def SendToMQTT(deviceId, json):

    #print("SendToMQTT")

    def on_publish(client, userdata, mid, reason_code, properties):
        # reason_code and properties will only be present in MQTTv5. It's always unset in MQTTv3
        try:
            userdata.remove(mid)
        except KeyError:
            print("on_publish() is called with a mid not present in unacked_publish")
            print("This is due to an unavoidable race-condition:")
            print("* publish() return the mid of the message sent.")
            print("* mid from publish() is added to unacked_publish by the main thread")
            print("* on_publish() is called by the loop_start thread")
            print("While unlikely (because on_publish() will be called after a network round-trip),")
            print(" this is a race-condition that COULD happen")
            print("")
            print("The best solution to avoid race-condition is using the msg_info from publish()")
            print("We could also try using a list of acknowledged mid rather than removing from pending list,")
            print("but remember that mid could be re-used !")

    unacked_publish = set()

    if not paho.mqtt.__version__.startswith("1."):
        mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqttc.on_publish = on_publish
    else:
        mqttc = mqtt.Client()

    mqttc.username_pw_set(username=mq_username,password=mq_password)

    mqttc.user_data_set(unacked_publish)
    print("Connecting to MQTT Broker")
    mqttc.connect(mq_broker_ip, mq_port, 60)
    mqttc.loop_start()
    print("MQTT Loop Start")

    # Wait for all message to be published
    while len(unacked_publish):
        time.sleep(0.1)

    # Send over MQTT
    msg_info = mqttc.publish(mq_topic_prefix+"/"+deviceId+"/infojson", json, qos=2, retain=True)
    unacked_publish.add(msg_info.mid)

    # Due to race-condition described above, the following way to wait for all publish is safer
    msg_info.wait_for_publish()

    mqttc.disconnect()
    mqttc.loop_stop()


def byte(str, byteNum):
    # https://stackoverflow.com/questions/5649407/hexadecimal-string-to-byte-array-in-python
    # Trapping for 'str' passed as 'None'
    if (str == None):
        return ''
    return str[byteNum * 2] + str[byteNum * 2 + 1]


def checkBM(data):
    check = False
    byteCheck = 0
    BMIFLLC = str("8d02")
    # print (byte(data,byteCheck))
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

    # BM Models (as of early 2024)

    # T (41, 47)    # TH (42, 56)
    # W (43, 57)    # W3/W4 (49)
    # SubHub (52)    # Hub (54)
    # DIY (58)    # BeeDar (63)

    # Current sample number from the device.
    sampleNumber = int(byte(data, byteNumAdvElapsed_2b), 16) + int(byte(data, byteNumAdvElapsed_2), 16)

    # Model
    modelNumber = int(byte(data, byteNumAdvdeviceModelIFllc_1), 16)

    # Version
    versionNumber = str(int(byte(data, byteNumAdvDeviceVersionMajor_1), 16)) + "." + str(int(byte(data, byteNumAdvDeviceVersionMinor_1), 16))

    print("  Model Number = {}, Version = {}, Sample = {}".format(modelNumber, versionNumber, sampleNumber))

    #defaults for non weigth devices
    realTimeWeight_lb = 0
    realTimeWeight_kg = 0

#    if modelNumber == 41 or modelNumber == 42 or modelNumber == 43:
#        continue


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

    #    print("  Scale R1 kg = {}".format(weightScaledR_kg))
    #    print("  Scale R2 kg = {}".format(weightScaledR2_kg))
    #    print("  Scale L1 kg = {}".format(weightScaledL_kg))
    #    print("  Scale L2 kg = {}".format(weightScaledL2_kg))
    #    print("  Scaled Total kg = {}".format(weightScaledR_kg+weightScaledR2_kg+weightScaledL_kg+weightScaledL2_kg))

        realTimeWeight_lb = ((int(byte(data, byteNumAdvRealtimeTotalWeight), 16) * 256 + int(byte(data, byteNumAdvRealtimeTotalWeight_SwarmState), 16) - 32767 ) / 100)
        realTimeWeight_kg = round(realTimeWeight_lb * lbtokg, 2)
        realTimeWeight_lb = round(realTimeWeight_lb, 2)

    #    print("  realTimeWeight kg = {}".format(realTimeWeight_kg))

    batteryPercent = int(byte(data, byteNumAdvBattery_1V2), 16)

    # Temps
    temperatureDegreesC = int(byte(data, byteNumAdvTemperature_2b) + byte(data, byteNumAdvTemperature_2), 16)
    temperatureDegreesC = (float(temperatureDegreesC) - 5000) / 100
    temperatureDegreesF = round((temperatureDegreesC * 9 / 5) + 32, 2)
    temperatureDegreesC = round(temperatureDegreesC, 2)

    # Humidity (0 for 41/47/49/52)
    if modelNumber == 41 or modelNumber == 47 or modelNumber == 49 or modelNumber == 52:
        humidityPercent = 0
    else:
        humidityPercent = int(byte(data, byteNumAdvHumidity))

    #print("    Weight = {} kg {} lb, TemperatureC = {} C {} F, Humidity = {} %, Battery = {} %".format(realTimeWeight_kg, realTimeWeight_lb, temperatureDegreesC, temperatureDegreesF, humidityPercent, batteryPercent))

    data = {"sampleNumber": sampleNumber,
            "modelNumber": modelNumber,
            "versionNumber": versionNumber,
            "sampleNumber": sampleNumber,
            "batteryPercent": batteryPercent,
            "realTimeWeight_lb": realTimeWeight_lb,
            "realTimeWeight_kg": realTimeWeight_kg,
            "temperatureDegreesC": temperatureDegreesC,
            "temperatureDegreesF": temperatureDegreesF,
            "humidityPercent": humidityPercent
            }

    #print (data)
    json_data = json.dumps(data)
    SendToMQTT(deviceId, json_data)


def processData(pdev):
    if (checkBM(pdev.getValueText(255))):
        print("  Device {} ({}), RSSI={} dB".format(pdev.addr, pdev.addrType, pdev.rssi))
        for (adtype, desc, value) in pdev.getScanData():
            print("    %s = %s" % (desc, value))

            # Trap for the BroodMinder ID
            if (desc == "Complete Local Name"):
                extractData(value, pdev.getValueText(255))

            # Trap for evertyhing
            extractData(value, pdev.getValueText(255))


class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            # print("  Discovered device {}".format(dev.addr))
            processData(dev)

        elif isNewData:
            # print("  Received data from {}".format(dev.addr))
            processData(dev)

scanner = Scanner().withDelegate(ScanDelegate())
devices = scanner.scan(30.0)
