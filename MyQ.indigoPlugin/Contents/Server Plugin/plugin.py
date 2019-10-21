#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import time
import requests
import logging

kCurDevVersCount = 1        # current version of plugin devices

API_BASE  = "https://api.myqdevice.com/api/v5"
APP_ID    = "JVM/G9Nwih5BwKgNCjLxiFUQxQijAebyyg8QUHr7JOrP+tuPb8iHfRHKwTmDzHOu"
userAgent = "Chamberlain/3.73"

COMMAND_CLOSE = "close"
COMMAND_OPEN = "open"

STATE_CLOSED = "closed"
STATE_CLOSING = "closing"
STATE_OPEN = "open"
STATE_OPENING = "opening"
STATE_STOPPED = "stopped"
STATE_TRANSITION = "transition"
STATE_UNKNOWN = "unknown"

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
    

    def startup(self):
        indigo.server.log(u"Starting MyQ")

        self.loginOK = False
        self.needsUpdate = True
        self.account_info = {}
        self.device_info = {}

        self.myqDevices = {}
        self.triggers = { }
        self.knownDevices = {}
        
        self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
        self.logger.debug(u"statusFrequency = " + str(self.statusFrequency))
        self.next_status_check = time.time()

        # Watch for changes to sensors associated with an opener
        indigo.devices.subscribeToChanges()

    @property
    def account_id(self):
        """Return the account ID."""
        return self.account_info["Account"]["Id"]

    def shutdown(self):
        indigo.server.log(u"Shutting down MyQ")


    def runConcurrentThread(self):

        try:
            while True:

                if self.needsUpdate or (time.time() > self.next_status_check):
                    self.getDevices()
                    self.next_status_check = time.time() + self.statusFrequency
                    self.needsUpdate = False

                self.sleep(1.0)

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
        self.needsUpdate = True
        
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

        if len(errorDict) > 0:
            return (False, valuesDict, errorDict)

        if not self.myqLogin(username=valuesDict['myqLogin'], password=valuesDict['myqPassword']):
            errorDict['myqLogin'] = u"Login to MyQ server failed, check login, password"
            errorDict['myqPassword'] = u"Login to MyQ server failed, check login, password"
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

            self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
            self.logger.debug(u"statusFrequency = " + str(self.statusFrequency))
            self.next_status_check = time.time() + self.statusFrequency

            self.getDevices()


    def availableDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):

        in_use =[]
        for dev in indigo.devices.iter(filter="self.myqOpener"):
            in_use.append(dev.address)

        retList =[]
        for myqID, myqName in self.knownDevices.iteritems():
            if myqID not in in_use:
                retList.append((myqID, myqName))

        if targetId:
            try:
                dev = indigo.devices[targetId]
                retList.insert(0, (dev.pluginProps["address"], self.knownDevices[int(dev.pluginProps["address"])]))
            except:
                pass

        self.logger.debug("availableDeviceList: retList = {}".format(retList))
        return retList



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
            self.logger.debug(u"actionControlDevice: Unlock {}".format(dev.name))
            self.changeDevice(dev, COMMAND_OPEN)

        elif action.deviceAction == indigo.kDeviceAction.Lock:
            self.logger.debug(u"actionControlDevice: Lock {}".format(dev.name))
            self.changeDevice(dev, COMMAND_CLOSE)

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.debug(u"actionControlDevice: Request Status")
            self.getDevices()

        else:
            self.logger.error(u"actionControlDevice: Unsupported action requested: {} for {}".format(action, dev.name))


    ########################################

    def myqLogin(self, username=None, password=None):

        if username == None or password == None:
            self.logger.debug(u"myqLogin failure, Username or Password not set")
            return False

        url = "{}/{}".format(API_BASE, 'Login')
        headers = {
                'User-Agent':       userAgent, 
                'Content-Type':     'application/json',
                'MyQApplicationId': APP_ID
        }
        payload = {
                'username': username, 
                'password': password
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            self.logger.debug(u"myqLogin response = {}".format(response.text))
            
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"myqLogin failure, request url: {}, RequestException: {}".format(url, err))
            self.securityToken = ""
            return False

        if (response.status_code != requests.codes.ok):
            self.logger.debug(u"myqLogin failure, status_code = {}".format(response.status_code))
            self.securityToken = ""
            return False        

        self.securityToken = response.json()['SecurityToken']
        self.logger.debug(u"myqLogin successful")
        self.loginOK = True
        
        url = "{}/{}".format(API_BASE, 'My')
        headers = {
                'User-Agent':       userAgent, 
                "Content-Type":     "application/json",
                'MyQApplicationId': APP_ID,
                'SecurityToken':    self.securityToken
        }
        params = {"expand": "account"}        

        try:
            response = requests.get(url, params=params, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.error(u"getDevices: RequestException: " + str(err))
            return False
        
        self.account_info = response.json()
        self.logger.threaddebug(u"myqLogin account_info = {}".format(self.account_info))

        return True

    ########################################

    def getDevices(self):
        
        if not self.myqLogin(username = self.pluginPrefs.get('myqLogin', None), password = self.pluginPrefs.get('myqPassword', None)):
            self.logger.debug(u"getDevices: MyQ Login Failure")
            return

        url = "{}/Accounts/{}/Devices".format(API_BASE, self.account_id)
        params = {
        }
        headers = {
            'SecurityToken':    self.securityToken,
            'User-Agent':       userAgent, 
            'Content-Type':     "application/json",
            'MyQApplicationId': APP_ID
        }    
        try:
            response = requests.get(url, params=params, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.error(u"getDevices: RequestException: " + str(err))
            return

        self.device_info = response.json()
        self.logger.threaddebug(u"getDevices device_info = {}".format(self.device_info))
        self.logger.debug(u"getDevices: {} Devices".format(len(self.device_info['items'])))

        for myqDevice in self.device_info['items']:

            family = myqDevice['device_family']
            name = myqDevice['name']
            myqID = myqDevice['serial_number']
            self.logger.debug(u"getDevices: device_family = {}, name = {}, serial_number = {}".format(family, name, myqID))
            
            if family == u'garagedoor':

                if not myqID in self.knownDevices:
                    self.knownDevices[myqID] = name
                    

                for dev in indigo.devices.iter(filter="self"):
                    self.logger.debug(u'Checking Opener Device: {} ({}) against {}'.format(dev.name, dev.address, myqID))
                    if dev.address == myqID:
                        state = myqDevice["state"].get("door_state")
                        dev.updateStateOnServer(key="doorStatus", value=state)
                        if state == STATE_CLOSED:
                           dev.updateStateOnServer(key="onOffState", value=True)  # closed is True (Locked)
                        else:
                            dev.updateStateOnServer(key="onOffState", value=False)   # anything other than closed is "Unlocked"
                        self.triggerCheck(dev)

                        break                    

            elif family == u'gateway':            # Gateway
                pass

            else:
                self.logger.debug(u'Unknown MyQ device: {}, family: {}'.format(name, family))


    ########################################

    def changeDeviceAction(self, pluginAction):
        self.logger.debug(u"changeDeviceAction, deviceId = {}, actionId = {}".format(pluginAction.deviceId, pluginAction.pluginTypeId))

        if pluginAction != None:
            myqDevice = indigo.devices[pluginAction.deviceId]
            myqActionId = pluginAction.pluginTypeId
            if myqActionId == "openDoor":
                self.changeDevice(myqDevice, COMMAND_OPEN)
            elif myqActionId == "closeDoor":
                self.changeDevice(myqDevice, COMMAND_CLOSE)
            else:
                self.logger.debug(u"changeDeviceAction, unknown myqActionId = %s" % myqActionId)


    def changeDevice(self, device, action_command):
        self.logger.debug(u"{}: changeDevice: new state = {}".format(device.name, action_command))
       
        url = "{}/Accounts/{}/Devices/{}/actions".format(API_BASE, self.account_id, device.address)
        data = {
            "action_type": action_command
        }        
        headers = {
            'SecurityToken':    self.securityToken,
            'User-Agent':       userAgent, 
            'Content-Type':     "application/json",
            'MyQApplicationId': APP_ID
        }    
        self.logger.threaddebug(u"{}: changeDevice: url = {}, data = = {}, headers = = {}".format(device.name, url, data, headers))
        try:
            response = requests.put(url, json=data, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.error(u"{}: changeDevice failure, RequestException: {}".format(device.name, err))
            return

        if (response.status_code != requests.codes.no_content):
            self.logger.error(u"{}: changeDevice failure, code: {}, response: {}".format(device.name, response.status_code, response.text))
            return

        # schedule an update to check on the movement
        self.next_status_check = time.time() + float(self.pluginPrefs.get('statusDelay', "30"))

