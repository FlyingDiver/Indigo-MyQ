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

kDoorClosed = 0
kDoorOpen   = 1

doorStateNames = ["Unknown", "Open", "Closed", "Stopped", "Opening", "Closing", "Unknown", "Disconnected", "Unknown", "Unknown"]

userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.116 Safari/537.36"

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


    def startup(self):
        indigo.server.log(u"Starting MyQ")

        self.myqDevices = {}
        self.triggers = { }

        self.updater = GitHubPluginUpdater(self)
        self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "24")) * 60.0 * 60.0
        self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
        self.next_update_check = time.time()

        self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
        self.logger.debug(u"statusFrequency = " + str(self.statusFrequency))
        self.next_status_check = time.time()

        # Watch for changes to sensors associated with an opener
        indigo.devices.subscribeToChanges()

        self.apiData = {
            "chamberlain" : {   "service" : "https://myqexternal.myqdevice.com",
                                "appID" : "JVM/G9Nwih5BwKgNCjLxiFUQxQijAebyyg8QUHr7JOrP+tuPb8iHfRHKwTmDzHOu"
                            },
            "craftsman" :   {   "service" : "https://craftexternal.myqdevice.com",
                                "appID" : "QH5AzY8MurrilYsbcG1f6eMTffMCm3cIEyZaSdK/TD/8SvlKAWUAmodIqa5VqVAs"
                            },
            "liftmaster" : {    "service" : "https://myqexternal.myqdevice.com",
                                "appID" : "JVM/G9Nwih5BwKgNCjLxiFUQxQijAebyyg8QUHr7JOrP+tuPb8iHfRHKwTmDzHOu"
                            },
                        }


    def shutdown(self):
        indigo.server.log(u"Shutting down MyQ")


    def runConcurrentThread(self):

        try:
            while True:

                if self.updateFrequency > 0:
                    if time.time() > self.next_update_check:
                        self.updater.checkForUpdate()
                        self.next_update_check = time.time() + self.updateFrequency

                if self.statusFrequency > 0:
                    if time.time() > self.next_status_check:
                        self.getDevices()
                        self.next_status_check = time.time() + self.statusFrequency

                self.sleep(60.0)

        except self.stopThread:
            pass

    def deviceStartComm(self, device):

        instanceVers = int(device.pluginProps.get('devVersCount', 0))
        if instanceVers >= kCurDevVersCount:
            self.logger.debug(device.name + u": Device Version is up to date")
        elif instanceVers < kCurDevVersCount:
            newProps = device.pluginProps
            newProps['IsLockSubType'] = True
            newProps["devVersCount"] = kCurDevVersCount
            device.replacePluginPropsOnServer(newProps)
            self.logger.debug(u"Updated " + device.name + " to version " + str(kCurDevVersCount))
        else:
            self.logger.error(u"Unknown device version: " + str(instanceVers) + " for device " + device.name)

        self.logger.debug("Adding Device %s (%d) to MyQ device list" % (device.name, device.id))
        assert device.id not in self.myqDevices
        self.myqDevices[device.id] = device

    def deviceStopComm(self, device):
        self.logger.debug("Removing Device %s (%d) from MyQ device list" % (device.name, device.id))
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
            self.logger.debug("\tmyqDoorSync:  %s is %s, linked sensor %s is %s" % (device.name, str(device.onState), sensor.name, str(sensor.onState)))

            if device.onState == sensor.onState:        # these values are supposed to be opposite due to difference between sensor and lock devices
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

        if len(valuesDict['myqLogin']) < 5:
            errorDict['myqLogin'] = u"Enter your MyQ login name (email address)"

        if len(valuesDict['myqPassword']) < 1:
            errorDict['myqPassword'] = u"Enter your MyQ login password"

        statusFrequency = int(valuesDict['statusFrequency'])
        if (0 < statusFrequency < 5) or (statusFrequency > (24 * 60)):
            errorDict['statusFrequency'] = u"Status frequency must be at least 5 min and less than 24 hours"

        updateFrequency = int(valuesDict['updateFrequency'])
        if (updateFrequency < 0) or (updateFrequency > 24):
            errorDict['updateFrequency'] = u"Update frequency is invalid - enter a valid number (between 0 and 24)"

        if len(errorDict) > 0:
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
            self.next_status_check = time.time()

    ################################################################################
    #
    # delegate methods for indigo.devices.subscribeToChanges()
    #
    ################################################################################

    def deviceDeleted(self, dev):
        indigo.PluginBase.deviceDeleted(self, dev)
#        self.logger.debug(u"deviceDeleted: %s " % dev.name)

        for myqDeviceId, myqDevice in sorted(self.myqDevices.iteritems()):
            sensorDev = myqDevice.pluginProps.get("sensor", "")
            if dev.id == int(sensorDev):
                self.logger.info(u"A device (%s) that was associated with a MyQ device has been deleted." % dev.name)
                newProps = myqDevice.pluginProps
                newProps["sensor"] = ""
                myqDevice.replacePluginPropsOnServer(newProps)


    def deviceUpdated(self, origDev, newDev):
        indigo.PluginBase.deviceUpdated(self, origDev, newDev)
#        self.logger.debug(u"deviceUpdated: %s " % newDev.name)

        for myqDeviceId, myqDevice in sorted(self.myqDevices.iteritems()):
#            self.logger.debug(u"\tchecking MyQ Device: %s " % myqDevice.name)
            try:
                sensorDev = int(myqDevice.pluginProps["sensor"])
            except:
                pass
            else:
                if origDev.id == sensorDev:
                    if origDev.onState == newDev.onState:
                        self.logger.debug(u"deviceUpdated: %s has not changed" % origDev.name)
                        return

                    self.logger.debug(u"deviceUpdated: %s has changed state: %s" % (origDev.name, str(newDev.onState)))
                    if newDev.onState:
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
            self.changeDevice(dev, kDoorClosed)

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.debug(u"actionControlDevice: \"%s\" Request Status" % dev.name)
            self.getDevices()

        else:
            self.logger.error(u"actionControlDevice: \"%s\" Unsupported action requested: %s" % (dev.name, str(action)))


    ########################################


    def myqLogin(self):

        self.username = self.pluginPrefs.get('myqLogin', None)
        self.password = self.pluginPrefs.get('myqPassword', None)
        self.brand = self.pluginPrefs.get('openerBrand', None)
        if (self.brand):
            self.service = self.apiData[self.brand]["service"]
            self.appID = self.apiData[self.brand]["appID"]

        payload = {'appId': self.appID, 'securityToken': 'null', 'username': self.username, 'password': self.password, 'culture': 'en'}
        login_url = self.service + '/api/user/validatewithculture'
        headers = {'User-Agent': userAgent}

        try:
            response = requests.get(login_url, params=payload, headers=headers)
            self.logger.debug(u"myqLogin: " + str(response.text))
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"myqLogin failure: RequestException: " + str(err))
            self.securityToken = ""
            return

        try:
            data = response.json()
        except:
            self.logger.debug(u"myqLogin failure: JSON Decode Error: " + str(err))
            self.securityToken = ""
            return

        if data['ReturnCode'] != '0':
            self.logger.debug(u"myqLogin failure: Bad return code: " + data['ErrorMessage'])
            self.securityToken = ""
            return

        self.securityToken = data['SecurityToken']

    ########################################

    def getDevices(self):

        self.myqLogin()

        if not self.securityToken:
            return

        url =  self.service + '/api/v4/userdevicedetails/get'
        params = {'appId':self.appID, 'securityToken':self.securityToken}
        headers = {'User-Agent': userAgent }
        try:
            response = requests.get(url, params=params, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"getDevices: RequestException: " + str(err))
            return

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"getDevices: Bad return code: " + data['ErrorMessage'])
            return

        self.logger.debug(u"getDevices: %d Devices" % len(data['Devices']))

        for myqDevice in data['Devices']:
            self.logger.debug(u"getDevices: MyQDeviceTypeId = %s, MyQDeviceTypeName = %s, DeviceId = %s" % (myqDevice['MyQDeviceTypeId'], myqDevice['MyQDeviceTypeName'], myqDevice['ConnectServerDeviceId']))

            # 2 = garage door, 5 = gate, 7 = MyQGarage(no gateway), 17 = Garage Door Opener WGDO

            if (myqDevice['MyQDeviceTypeId'] == 2) or (myqDevice['MyQDeviceTypeId'] == 5) or (myqDevice['MyQDeviceTypeId'] == 7) or (myqDevice['MyQDeviceTypeId'] == 17):

                name = u"Unknown"
                state = -1

                for attr in myqDevice['Attributes']:
                    self.logger.debug(u'\t"%s" = "%s"' % (attr[u'AttributeDisplayName'], attr[u'Value']))

                    if attr[u'AttributeDisplayName'] == u'desc':
                        name = attr[u'Value']
                    elif attr[u'AttributeDisplayName'] == u'doorstate':
                        state = int(attr[u'Value'])
                if state > (len(doorStateNames) - 1):
                    self.logger.error(u"getDevices: Opener %s (%s), state out of range: %i" % (name, myqDevice['ConnectServerDeviceId'], state))
                    state = 0       # unknown high states
                elif state == -1:
                    self.logger.error(u"getDevices: Opener %s (%s), state unknown" % (name, myqDevice['ConnectServerDeviceId']))
                    state = 0       # unknown state

                iterator = indigo.devices.iter(filter="self")
                for dev in iterator:
                    if dev.address == myqDevice['ConnectServerDeviceId']:
                        newState = doorStateNames[state]
                        if dev.states["doorStatus"] != newState:
                            self.logger.info(u"%s %s is now %s (%d)" % (myqDevice['MyQDeviceTypeName'], name, newState, state))
                        dev.updateStateOnServer(key="doorStatus", value=newState)
                        if state == 2:
                           dev.updateStateOnServer(key="onOffState", value=True)  # closed is True
                        else:
                            dev.updateStateOnServer(key="onOffState", value=False)   # anything other than closed is "unlocked"
                        self.triggerCheck(dev)
                        break
                else:                           # Python syntax weirdness - this else belongs to the for loop!

                    # New MyQ device found, create it and set current state

                    newdev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                        address=myqDevice['ConnectServerDeviceId'],
                        description = "Opener Device auto-created by MyQ plugin from gateway information",
                        deviceTypeId='myqOpener',
                        name=name)
                    newdev.updateStateOnServer(key="doorStatus", value=doorStateNames[state])
                    if state == 2:
                        newdev.updateStateOnServer(key="onOffState", value=True)
                    else:
                        newdev.updateStateOnServer(key="onOffState", value=False)
                    self.logger.debug(u'Created New Opener Device: %s (%s)' % (newdev.name, newdev.address))
                    self.logger.info(u"%s %s is %s (%d)" % (myqDevice['MyQDeviceTypeName'], name, doorStateNames[state], state))

            elif myqDevice['MyQDeviceTypeId'] == 3:            # Light Switch?
                for attr in myqDevice['Attributes']:
                    self.logger.debug(u'\t"%s" = "%s"' % (attr[u'AttributeDisplayName'], attr[u'Value']))

            else:
                for attr in myqDevice['Attributes']:
                    self.logger.debug(u'\t"%s" = "%s"' % (attr[u'AttributeDisplayName'], attr[u'Value']))


    ########################################

    def changeDeviceAction(self, pluginAction):

        if pluginAction != None:
            myqDevice = indigo.devices[pluginAction.deviceId]
            myqActionId = pluginAction.pluginTypeId
            if myqActionId == "openDoor":
                self.changeDevice(myqDevice, kDoorOpen)
            elif myqActionId == "closeDoor":
                self.changeDevice(myqDevice, kDoorClosed)
            else:
                self.logger.debug(u"changeDeviceAction, unknown myqActionId = %s" % myqActionId)

    def changeDevice(self, device, state):
        self.logger.debug(u"changeDevice: %s, state = %d" % (device.name, state))

        self.myqLogin()

        url = self.service + '/api/deviceattribute/putdeviceattribute'
        payload = {
           'ApplicationId': self.appID,
           'AttributeName': 'desireddoorstate',
           'DeviceId': device.address,
           'AttributeValue': state,
           'SecurityToken': self.securityToken
           }
        headers = {'User-Agent': userAgent}
        try:
            response = requests.put(url, data=payload, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"changeDevice: RequestException: " + str(err))
            return

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"changeDevice: Bad return code: " + data['ErrorMessage'])

        # schedule an update to check on the movement
        self.next_status_check = time.time() + float(self.pluginPrefs.get('statusDelay', "30"))

