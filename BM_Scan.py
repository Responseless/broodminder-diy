#!/usr/bin/python2.7
__author__ = "Jesse Ross-Jones"
__license__ = "Public Domain"
__version__ = "1.0"

## Tested with Python 2.7
## Using bluepy, scan for bluetooth devices for 15 seconds.
## Search list of found devices and for devices matching broodminder manufacture data
## Decode and print the advertising data
##
## DStrickler Sat, Apr 14, 2018
## Use bluepy module from https://github.com/IanHarvey/bluepy (has install instructions)
## Needs to be run with "sudo" so that the BLE library can sniff out devices. Otherwise will error out.
## On Ubuntu, I've found that I need to install the bluepy source from scratch to get it to work.
##
## DStrickler Mon, Apr 16, 2018
## Sniffs out all devices, but doesn't exclude weight when not a 43 device.
##
## DStrickler Mon, Jul 23, 2018
## Added preliminary upload test with Alpha API call (/api_public).
## Uploads temperature, humidity, weight and battery from all the BroodMinder
## devices that show up in a BLE scan.
## Note I am using an unpublished API call to upload data with this code.
##
## DStrickler Wed, Jan 16, 2019
## Added support for uploading the sample info as well.
##
## Responseless May, 2024
## Cleanup code and fix errors with libraries, new py version, instant return on results. kg/lb calulations
## Updated calculations based on info from https://doc.mybroodminder.com/87_physics_and_tech_stuff/#ble-advertising-information
## Tested only with device 49


from bluepy.btle import Scanner, DefaultDelegate

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
    # print(byte(data,byteCheck))
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
    byteNumAdvTemperature_2 = 18 - offset
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
    version = str(int(byte(data, byteNumAdvDeviceVersionMajor_1), 16)) + "." + str(int(byte(data, byteNumAdvDeviceVersionMinor_1), 16))
 
    print("  Model Number = {}, Version = {}".format(modelNumber, version))

    if modelNumber == 41 or modelNumber == 42 or modelNumber == 43:
      pass


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

      print("  Scale R1 kg = {}".format(weightScaledR_kg))
      print("  Scale R2 kg = {}".format(weightScaledR2_kg))
      print("  Scale L1 kg = {}".format(weightScaledL_kg))
      print("  Scale L2 kg = {}".format(weightScaledL2_kg))
      print("  Scaled Total kg = {}".format(weightScaledR_kg+weightScaledR2_kg+weightScaledL_kg+weightScaledL2_kg))

      realTimeWeight_lb = ((int(byte(data, byteNumAdvRealtimeTotalWeight_SwarmState + 1), 16) * 256 + int(byte(data, byteNumAdvRealtimeTotalWeight_SwarmState), 16) - 32767 ) / 100)
      realTimeWeight_kg = realTimeWeight_lb * lbtokg

      print("  realTimeWeight kg = {}".format(realTimeWeight_kg))

    batteryPercent = int(byte(data, byteNumAdvBattery_1V2), 16)

    # Temps
    temperatureDegreesC = int(byte(data, byteNumAdvTemperature_2 + 1) + byte(data, byteNumAdvTemperature_2), 16)
    temperatureDegreesC = (float(temperatureDegreesC) - 5000) / 100
    temperatureDegreesF = round((temperatureDegreesC * 9 / 5) + 32, 1)

    # Humidity (0 for 41/47/49/52)
    if modelNumber == 41 or modelNumber == 47 or modelNumber == 49 or modelNumber == 52:
        humidityPercent = 0
    else:
        humidityPercent = byte(data, byteNumAdvHumidity)


    print("    Weight = {} kg {} lb, TemperatureC = {} C {} F, Humidity = {} %, Battery = {} %".format(realTimeWeight_kg, realTimeWeight_lb, temperatureDegreesC, temperatureDegreesF, humidityPercent, batteryPercent))


def processData(pdev):
    if (checkBM(pdev.getValueText(255))):
        print("  Device {} ({}), RSSI={} dB".format(pdev.addr, pdev.addrType, pdev.rssi))
        for (adtype, desc, value) in pdev.getScanData():
            print("    %s = %s" % (desc, value))

            # Trap for the BroodMinder ID
            if (desc == "Complete Local Name"):
                extractData(value, pdev.getValueText(255))

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            print("  Discovered device {}".format(dev.addr))

        elif isNewData:
            print("  Received data from {}".format(dev.addr))
            processData(dev)

scanner = Scanner().withDelegate(ScanDelegate())
devices = scanner.scan(30.0)