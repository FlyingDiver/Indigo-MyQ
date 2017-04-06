#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
## Python to interface with MyQ garage doors.
## based on https://github.com/Einstein42/myq-garage

import sys
import time
import requests
import logging

from requests.auth import HTTPBasicAuth
from requests.utils import quote

from ghpu import GitHubPluginUpdater

kCurDevVersCount = 1        # current version of plugin devices

kDoorClose  = '0'
kDoorOpen   = '1'

doorStateNames = ["Unknown", "Open", "Closed", "Stopped", "Opening", "Closing", "Unknown", "Disconnected", "Unknown", "Unknown"]

userAgent = "Chamberlain/3773 (iPhone; iOS 10.0.1; Scale/2.00)"

################################################################################
class Plugin(indigo.PluginBase):

    ########################################
    # Main Plugin methods
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)

        try:
            self.logLevel = int(self.pluginPrefs[u"logLevel"])
        except:
            self.logLevel = logging.INFO
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(u"logLevel = " + str(self.logLevel))
        
        self.loginOK = False


    def startup(self):
        indigo.server.log(u"Starting MyQ")

        self.myqDevices = {}
        self.triggers = { }

        self.apiData = {
            "chamberlain" : {   "service" : "https://myqexternal.myqdevice.com",
                                "appID" : "Vj8pQggXLhLy0WHahglCD4N1nAkkXQtGYpq2HrHD7H1nvmbT55KqtN6RSF4ILB/i"
                            },
            "craftsman" :   {   "service" : "https://craftexternal.myqdevice.com",
                                "appID" : "eU97d99kMG4t3STJZO/Mu2wt69yTQwM0WXZA5oZ74/ascQ2xQrLD/yjeVhEQccBZ"
                            },
            "liftmaster" : {    "service" : "https://myqexternal.myqdevice.com",
                                "appID" : "Vj8pQggXLhLy0WHahglCD4N1nAkkXQtGYpq2HrHD7H1nvmbT55KqtN6RSF4ILB/i"
                            },
                        }

        self.updater = GitHubPluginUpdater(self)
        self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "24")) * 60.0 * 60.0
        self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
        self.next_update_check = time.time()

        self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
        self.logger.debug(u"statusFrequency = " + str(self.statusFrequency))
        self.next_status_check = time.time()

        # Watch for changes to sensors associated with an opener
        indigo.devices.subscribeToChanges()


    def shutdown(self):
        indigo.server.log(u"Shutting down MyQ")


    def runConcurrentThread(self):

        try:
            while True:

                if self.updateFrequency > 0:
                    if time.time() > self.next_update_check:
                        self.updater.checkForUpdate()
                        self.next_update_check = time.time() + self.updateFrequency

                if time.time() > self.next_status_check:
                    self.getDevices()
                    self.next_status_check = time.time() + self.statusFrequency

                self.sleep(60.0)

        except self.stopThread:
            pass

    def deviceStartComm(self, device):

        instanceVers = int(device.pluginProps.get('devVersCount', 0))
        if instanceVers >= kCurDevVersCount:
            self.logger.debug(u"deviceStartComm: " + device.name + u": Device Version is up to date")
        elif instanceVers < kCurDevVersCount:
            newProps = device.pluginProps
            newProps['IsLockSubType'] = True
            newProps["devVersCount"] = kCurDevVersCount
            device.replacePluginPropsOnServer(newProps)
            device.stateListOrDisplayStateIdChanged()
            self.logger.debug(u"deviceStartComm: Updated " + device.name + " to version " + str(kCurDevVersCount))
        else:
            self.logger.error(u"deviceStartComm: Unknown device version: " + str(instanceVers) + " for device " + device.name)

        self.logger.debug("deviceStartComm: Adding Device %s (%d) to MyQ device list" % (device.name, device.id))
        assert device.id not in self.myqDevices
        self.myqDevices[device.id] = device

    def deviceStopComm(self, device):
        self.logger.debug("deviceStopComm: Removing Device %s (%d) from MyQ device list" % (device.name, device.id))
        assert device.id in self.myqDevices
        del self.myqDevices[device.id]


    def triggerStartProcessing(self, trigger):
        self.logger.debug("Adding Trigger %s (%d) - %s" % (trigger.name, trigger.id, trigger.pluginTypeId))
        assert trigger.id not in self.triggers
        self.triggers[trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug("Removing Trigger %s (%d)" % (trigger.name, trigger.id))
        assert trigger.id in self.triggers
        del self.triggers[trigger.id]

    def triggerCheck(self, device):
        try:
            sensor = indigo.devices[int(device.pluginProps["sensor"])]
        except:
            self.logger.debug("Skipping triggers, no linked sensor for MyQ device %s" % (device.name))
            return

        for triggerId, trigger in sorted(self.triggers.iteritems()):
            self.logger.debug("Checking Trigger %s (%s), Type: %s" % (trigger.name, trigger.id, trigger.pluginTypeId))
            if isinstance(sensor, indigo.SensorDevice):
                sensor_state = sensor.onState
            elif isinstance(sensor, indigo.MultiIODevice):
                sensor_state = not sensor.states["binaryInput1"] # I/O devices are opposite from sensors in terms of the state binary
            
            self.logger.debug("\tmyqDoorSync:  %s is %s, linked sensor %s is %s" % (device.name, str(device.onState), sensor.name, str(sensor_state)))

            if device.onState == sensor_state:        # these values are supposed to be opposite due to difference between sensor and lock devices
                indigo.trigger.execute(trigger)         # so execute the out of sync trigger when they're not opposite


    ########################################
    # Menu Methods
    ########################################

    def checkForUpdates(self):
        self.updater.checkForUpdate()

    def updatePlugin(self):
        self.updater.update()

    def forceUpdate(self):
        self.updater.update(currentVersion='0.0.0')

    ########################################
    # ConfigUI methods
    ########################################

    def validatePrefsConfigUi(self, valuesDict):
        self.logger.debug(u"validatePrefsConfigUi called")
        errorDict = indigo.Dict()

        try:
            self.logLevel = int(valuesDict[u"logLevel"])
        except:
            self.logLevel = logging.INFO
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(u"logLevel = " + str(self.logLevel))

        if len(valuesDict['myqLogin']) < 5:
            errorDict['myqLogin'] = u"Enter your MyQ login name (email address)"

        if len(valuesDict['myqPassword']) < 1:
            errorDict['myqPassword'] = u"Enter your MyQ login password"

        statusFrequency = int(valuesDict['statusFrequency'])
        if (statusFrequency < 5) or (statusFrequency > (24 * 60)):
            errorDict['statusFrequency'] = u"Status frequency must be at least 5 min and no more than 24 hours"

        updateFrequency = int(valuesDict['updateFrequency'])
        if (updateFrequency < 0) or (updateFrequency > 24):
            errorDict['updateFrequency'] = u"Update frequency is invalid - enter a valid number (between 0 and 24 hours)"

        if len(errorDict) > 0:
            return (False, valuesDict, errorDict)

        if not self.myqLogin(username=valuesDict['myqLogin'], password=valuesDict['myqPassword'], brand=valuesDict['openerBrand']):
            errorDict['myqLogin'] = u"Login to MyQ server failed, check login, password, and brand"
            errorDict['myqPassword'] = u"Login to MyQ server failed, check login, password, and brand"
            return (False, valuesDict, errorDict)

        return (True, valuesDict)


    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            try:
                self.logLevel = int(valuesDict[u"logLevel"])
            except:
                self.logLevel = logging.INFO
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(u"logLevel = " + str(self.logLevel))

            self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "24")) * 60.0 * 60.0
            self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
            self.next_update_check = time.time()

            self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
            self.logger.debug(u"statusFrequency = " + str(self.statusFrequency))
            self.next_status_check = time.time() + self.statusFrequency

            self.getDevices()

    ################################################################################
    #
    # delegate methods for indigo.devices.subscribeToChanges()
    #
    ################################################################################

    def deviceDeleted(self, dev):
        indigo.PluginBase.deviceDeleted(self, dev)
        self.logger.debug(u"deviceDeleted: %s " % dev.name)

        for myqDeviceId, myqDevice in sorted(self.myqDevices.iteritems()):
            try:
                sensorDev = myqDevice.pluginProps["sensor"]
            except:
                return
            
            try:
                sensorID = int(sensorDev)
            except:
                return
                
            if dev.id == sensorID:
                self.logger.info(u"A device (%s) that was associated with a MyQ device has been deleted." % dev.name)
                newProps = myqDevice.pluginProps
                newProps["sensor"] = ""
                myqDevice.replacePluginPropsOnServer(newProps)


    def deviceUpdated(self, origDev, newDev):
        indigo.PluginBase.deviceUpdated(self, origDev, newDev)

        for myqDeviceId, myqDevice in sorted(self.myqDevices.iteritems()):
            try:
                sensorDev = int(myqDevice.pluginProps["sensor"])
            except:
                pass
            else:
                if origDev.id == sensorDev:
                    if isinstance(newDev, indigo.SensorDevice):
                        old_sensor_state = origDev.onState
                        sensor_state = newDev.onState
                    elif isinstance(newDev, indigo.MultiIODevice):
                        old_sensor_state =  not origDev.states["binaryInput1"] # I/O devices are opposite from sensors in terms of the state binary
                        sensor_state = not newDev.states["binaryInput1"] # I/O devices are opposite from sensors in terms of the state binary
                    else:    
                        self.logger.error(u"deviceUpdated: unknown device type for %s" % origDev.name)
                        
                    if old_sensor_state == sensor_state:
                        self.logger.debug(u"deviceUpdated: %s has not changed" % origDev.name)
                        return

                    self.logger.debug(u"deviceUpdated: %s has changed state: %s" % (origDev.name, str(sensor_state)))
                    if sensor_state:
                        myqDevice.updateStateOnServer(key="onOffState", value=False)   # sensor "On" means the door's open, which is False for lock type devices (unlocked)
                    else:
                        myqDevice.updateStateOnServer(key="onOffState", value=True)   # sensor "Off" means the door's closed, which is True for lock type devices (locked)
                    self.triggerCheck(myqDevice)

    ########################################

    def actionControlDevice(self, action, dev):

        if action.deviceAction == indigo.kDeviceAction.Unlock:
            self.logger.debug(u"actionControlDevice: \"%s\" Unlock" % dev.name)
            self.changeDevice(dev, kDoorOpen)

        elif action.deviceAction == indigo.kDeviceAction.Lock:
            self.logger.debug(u"actionControlDevice: \"%s\" Lock" % dev.name)
            self.changeDevice(dev, kDoorClose)

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.debug(u"actionControlDevice: \"%s\" Request Status" % dev.name)
            self.getDevices()

        else:
            self.logger.error(u"actionControlDevice: \"%s\" Unsupported action requested: %s" % (dev.name, str(action)))


    ########################################


    def myqLogin(self, username=None, password=None, brand=None):

        if username == None or password == None or brand == None:
            self.logger.debug(u"myqLogin failure, Username or Password not set")
            return False

        url = self.apiData[brand]["service"] + '/api/v4/user/validate'
        headers = {
                'User-Agent':       userAgent, 
                "BrandId":          "2",
                "ApiVersion":       "4.1",
                "Culture":          "en",
                'MyQApplicationId': self.apiData[brand]["appID"]
        }
        payload = {
                'username': username, 
                'password': password
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"myqLogin failure, request url = %s" % (url))
            self.logger.error(u"myqLogin failure, RequestException: %s" % (str(err)))
            self.securityToken = ""
            return False

        if (response.status_code != requests.codes.ok):
            self.logger.debug(u"myqLogin failure, Enum err code %s" % (response.status_coderl))
            self.securityToken = ""
            return False        

        try:
            data = response.json()
        except:
            self.logger.error(u"myqLogin failure, JSON Decode Error")
            self.securityToken = ""
            return False

        if data['ReturnCode'] != '0':
            self.logger.error(u"myqLogin failure, Bad return code: %s" % (data['ErrorMessage']))
            self.securityToken = ""
            return False

        self.securityToken = data['SecurityToken']
        self.logger.debug(u"myqLogin successfull")
        self.loginOK = True
        return True

    ########################################

    def getDevices(self):

        brand = self.pluginPrefs.get('openerBrand', None)
        
        if not self.myqLogin(username = self.pluginPrefs.get('myqLogin', None), password = self.pluginPrefs.get('myqPassword', None), brand=brand):
            self.logger.debug(u"getDevices: MyQ Login Failure")
            return

        url =  self.apiData[brand]["service"] + '/api/v4/UserDeviceDetails/Get'
        params = {'appId':self.apiData[brand]["appID"], 'securityToken':self.securityToken}
        headers = {'User-Agent': userAgent }
        try:
            response = requests.get(url, params=params, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.error(u"getDevices: RequestException: " + str(err))
            return

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.error(u"getDevices: Bad return code: " + data['ErrorMessage'])
            return

        self.logger.debug(u"getDevices: %d Devices" % len(data['Devices']))

        for myqDevice in data['Devices']:
            self.logger.debug(u"getDevices: MyQDeviceTypeId = %s, MyQDeviceTypeName = %s, DeviceId = %s" % (myqDevice['MyQDeviceTypeId'], myqDevice['MyQDeviceTypeName'], myqDevice['MyQDeviceId']))

            # 2 = garage door, 5 = gate, 7 = MyQGarage(no gateway), 17 = Garage Door Opener WGDO

            if myqDevice['MyQDeviceTypeId'] == 1:            # Gateway
                pass

            elif (myqDevice['MyQDeviceTypeId'] == 2) or (myqDevice['MyQDeviceTypeId'] == 5) or (myqDevice['MyQDeviceTypeId'] == 7) or (myqDevice['MyQDeviceTypeId'] == 17):

                myqID = myqDevice['MyQDeviceId']
                state = -1

                for attr in myqDevice['Attributes']:

                    if attr[u'AttributeDisplayName'] == u'desc':
                        descAttr = attr[u'Value']
                    elif attr[u'AttributeDisplayName'] == u'name':
                        nameAttr = attr[u'Value']
                    elif attr[u'AttributeDisplayName'] == u'doorstate':
                        state = int(attr[u'Value'])

                name = "%s (%s)" % (descAttr, nameAttr)

                if state > (len(doorStateNames) - 1):
                    self.logger.error(u"getDevices: Opener %s (%s), state out of range: %i" % (name, myqDevice['MyQDeviceId'], state))
                    state = 0       # unknown high states
                elif state == -1:
                    self.logger.error(u"getDevices: Opener %s (%s), state unknown" % (name, myqDevice['MyQDeviceId']))
                    state = 0       # unknown state

                found = False
                iterator = indigo.devices.iter(filter="self")
                for dev in iterator:
                    self.logger.debug(u'Checking Opener Device: %s (%s) against %s' % (dev.name, dev.address, myqID))
                    if int(dev.address) == int(myqID):
                        found = True
                        newState = doorStateNames[state]
                        if dev.states["doorStatus"] != newState:
                            self.logger.info(u"%s %s is now %s (%d)" % (myqDevice['MyQDeviceTypeName'], name, newState, state))
                            dev.updateStateOnServer(key="doorStatus", value=newState)
                        if state == 2:
                           dev.updateStateOnServer(key="onOffState", value=True)  # closed is True (Locked)
                        else:
                            dev.updateStateOnServer(key="onOffState", value=False)   # anything other than closed is "Unlocked"
                        self.triggerCheck(dev)
                        break
                        
                if not found:
                    self.logger.debug(u'Unknown MyQ Device: %s' % (myqID))

                    # New MyQ device found, create it and set current state

                    try:
                        newdev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                            address=myqID,
                            description = "Opener Device auto-created by MyQ plugin from gateway information",
                            deviceTypeId='myqOpener',
                            name=name)
                    except Exception as err:
                        self.logger.error(u'Error Creating Opener Device: %s (%s)' % (name, myqDevice[u'MyQDeviceId']))
                        continue
                    
                    newdev.updateStateOnServer(key="doorStatus", value=doorStateNames[state])
                    if state == 2:
                        newdev.updateStateOnServer(key="onOffState", value=True)
                    else:
                        newdev.updateStateOnServer(key="onOffState", value=False)
                    self.logger.debug(u'Created New Opener Device: %s (%s)' % (newdev.name, newdev.address))
                    self.logger.info(u"%s %s is %s (%d)" % (myqDevice['MyQDeviceTypeName'], name, doorStateNames[state], state))

            elif myqDevice['MyQDeviceTypeId'] == 3:            # Light Switch?
                pass
#                for attr in myqDevice['Attributes']:
#                    self.logger.debug(u'\t"%s" = "%s"' % (attr[u'AttributeDisplayName'], attr[u'Value']))

            else:
                for attr in myqDevice['Attributes']:
                    self.logger.debug(u'\t"%s" = "%s"' % (attr[u'AttributeDisplayName'], attr[u'Value']))


    ########################################

    def changeDeviceAction(self, pluginAction):
        self.logger.debug(u"changeDeviceAction, deviceId = %s, actionId = %s" % (pluginAction.deviceId, pluginAction.pluginTypeId))

        if pluginAction != None:
            myqDevice = indigo.devices[pluginAction.deviceId]
            myqActionId = pluginAction.pluginTypeId
            if myqActionId == "openDoor":
                self.changeDevice(myqDevice, kDoorOpen)
            elif myqActionId == "closeDoor":
                self.changeDevice(myqDevice, kDoorClose)
            else:
                self.logger.debug(u"changeDeviceAction, unknown myqActionId = %s" % myqActionId)

    def changeDevice(self, device, state):
        self.logger.debug(u"changeDevice: %s, state = %s" % (device.name, state))

        brand = self.pluginPrefs.get('openerBrand', None)
        
        if not self.myqLogin(username = self.pluginPrefs.get('myqLogin', None), password = self.pluginPrefs.get('myqPassword', None), brand=brand):
            self.logger.debug(u"changeDevice: MyQ Login Failure")
            return
            
        url = self.apiData[brand]["service"] + '/api/v4/DeviceAttribute/PutDeviceAttribute'
        headers = {
            'SecurityToken':    self.securityToken,
            'MyQApplicationId': self.apiData[brand]["appID"],
            'User-Agent': userAgent
        }    
        payload = {
            'attributeName':    "desireddoorstate",
            'myQDeviceId':      int(device.address),
            'AttributeValue':   state,
        }
        
        try:
            response = requests.put(url, data=payload, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.error(u"changeDevice failure, RequestException: %s" % (str(err)))
            return

        if (response.status_code != requests.codes.ok):
            self.logger.error(u"changeDevice failure, Request error code: %s" % (response.status_code))
            return
            
        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"changeDevice: Bad return code: " + data['ErrorMessage'])

        # schedule an update to check on the movement
        self.next_status_check = time.time() + float(self.pluginPrefs.get('statusDelay', "30"))

