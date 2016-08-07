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

kCurDevVersCount = 0        # current version of plugin devices

kDoorClosed = 0
kDoorOpen   = 1
kswitchOff  = 0
kswitchOn   = 1

doorStateNames = ["Unknown", "Open", "Closed", "Stopped", "Opening", "Closing", "Unknown", "Disconnected"]

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

        self.updater = GitHubPluginUpdater(self)
        self.updateFrequency = float(self.pluginPrefs.get('updateFrequency', "24")) * 60.0 * 60.0
        self.logger.debug(u"updateFrequency = " + str(self.updateFrequency))
        self.next_update_check = time.time()

        self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
        self.logger.debug(u"statusFrequency = " + str(self.updateFrequency))
        self.next_status_check = time.time()

        self.apiData = {
            "chamberlain" : {   "service" : "https://myqexternal.myqdevice.com",
                                "appID" : "Vj8pQggXLhLy0WHahglCD4N1nAkkXQtGYpq2HrHD7H1nvmbT55KqtN6RSF4ILB%2fi"
                            },
            "craftsman" :   {   "service" : "https://craftexternal.myqdevice.com",
                                "appID" : "eU97d99kMG4t3STJZO/Mu2wt69yTQwM0WXZA5oZ74/ascQ2xQrLD/yjeVhEQccBZ"
                            },
            "liftmaster" : {    "service" : "https://myqexternal.myqdevice.com",
                                "appID" : "Vj8pQggXLhLy0WHahglCD4N1nAkkXQtGYpq2HrHD7H1nvmbT55KqtN6RSF4ILB%2fi"
                            },
                        }

        self.triggers = { }


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

                self.sleep(1.0)

        except self.stopThread:
            pass


    ####################


    def triggerStartProcessing(self, trigger):
        self.logger.debug("Adding Trigger %s (%d) - %s" % (trigger.name, trigger.id, trigger.pluginTypeId))
        assert trigger.id not in self.triggers
        self.triggers[trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug("Removing Trigger %s (%d)" % (trigger.name, trigger.id))
        assert trigger.id in self.triggers
        del self.triggers[trigger.id]

    def triggerCheck(self, device):
        for triggerId, trigger in sorted(self.triggers.iteritems()):
            self.logger.debug("\tChecking Trigger %s (%s), Type: %s" % (trigger.name, trigger.id, trigger.pluginTypeId))


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
        if (statusFrequency < 5) or (statusFrequency > (24 * 60)):
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

    ########################################

    def actionControlDimmerRelay(self, action, dev):

        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.logger.debug(u"actionControlDimmerRelay: \"%s\" On" % dev.name)
            self.changeDevice(dev, kDoorOpen)

        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.logger.debug(u"actionControlDimmerRelay: \"%s\" Off" % dev.name)
            self.changeDevice(dev, kDoorClosed)

        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            self.logger.debug(u"actionControlDimmerRelay: \"%s\" Toggle" % dev.name)
            if dev.isOn:
                self.changeDevice(dev, kDoorClosed)
            else:
                self.changeDevice(dev, kDoorOpen)

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.debug(u"actionControlDimmerRelay: \"%s\" Request Status" % dev.name)
            self.getDevices()

    ########################################


    def myqLogin(self):

        self.username = self.pluginPrefs.get('myqLogin', None)
        self.password = self.pluginPrefs.get('myqPassword', None)
        self.brand = self.pluginPrefs.get('openerBrand', None)
        if (self.brand):
            self.service = self.apiData[self.brand]["service"]
            self.appID = self.apiData[self.brand]["appID"]


        url = self.service + '/Membership/ValidateUserWithCulture?appid=' + self.appID + '&securityToken=null&username=' + self.username + '&password=' + self.password + '&culture=en'

        try:
            response = requests.get(url)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"myqLogin: RequestException: " + str(err))
            return

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"myqLogin: Bad return code: " + data['ErrorMessage'])
            return

        self.securityToken = data['SecurityToken']
        self.logger.debug(u"myqLogin: Success, Brand = %s, SecurityToken = %s" % (data[u'BrandName'], self.securityToken))

    ########################################

    def getDevices(self):

        self.myqLogin()

        url =  self.service + '/api/UserDeviceDetails?appId=' + self.appID + '&securityToken=' + self.securityToken
        try:
            response = requests.get(url)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"getDevices: RequestException: " + str(err))
            return

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"getDevices: Bad return code: " + data['ErrorMessage'])
            return

        self.logger.debug(u"getDevices: %d Devices" % len(data['Devices']))

        for device in data['Devices']:
            self.logger.debug(u"getDevices: MyQDeviceTypeId = %s, DeviceId = %s" % (device['MyQDeviceTypeId'], device['DeviceId']))

            if (device['MyQDeviceTypeId'] == 2) or (device['MyQDeviceTypeId'] == 5) or (device['MyQDeviceTypeId'] == 7):            # MyQDeviceTypeId Door == 2, Gate == 5, Door? == 7
                myqID = device['DeviceId']
                name = self.getDeviceName(myqID)
                state = self.getDeviceState(myqID)
                if state > 7:
                    self.logger.error(u"getDevices: Opener %s (%s), state out of range: %i" % (name, myqID, state))
                    state = 0       # unknown high states
                else:
                    self.logger.debug(u"getDevices: Opener %s (%s), state = %i" % (name, myqID, state))

                iterator = indigo.devices.iter(filter="self")
                for dev in iterator:
                    if dev.address == myqID:
                        dev.updateStateOnServer(key="doorStatus", value=doorStateNames[int(state)])
                        if state == 2:
                            dev.updateStateOnServer(key="onOffState", value=False)  # closed is off
                        else:
                            dev.updateStateOnServer(key="onOffState", value=True)   # anything other than closed is "on"
                        break
                else:                           # Python syntax weirdness - this else belongs to the for loop!
                    newdev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                        address=myqID,
                        description = "Opener Device auto-created by MyQ plugin from gateway information",
                        deviceTypeId='myqOpener',
                        name=name)
                    newdev.updateStateOnServer(key="doorStatus", value=doorStateNames[int(state)])
                    self.logger.debug(u'Created New Opener Device: %s (%s)' % (newdev.name, newdev.address))

#            elif device['MyQDeviceTypeId'] == 3:            # Switch == 3?
#               myqID = device['DeviceId']
#               name = self.getDeviceName(myqID)
#               state = self.getDeviceState(myqID)
#               self.logger.debug(u"getDevices: Switch = %s (%s), data = %s" % (name, myqID, str(device)))
#
#                iterator = indigo.devices.iter(filter="self")
#                for dev in iterator:
#                    if dev.address == myqID:
#                        break
#                else:                           # Python syntax weirdness - this else belongs to the for loop!
#                    newdev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
#                        address=myqID,
#                        description = "Switch Device auto-created by MyQ plugin from gateway information",
#                        deviceTypeId='myqSwitch',
#                        name=name)
#                   newdev.updateStateOnServer(key="doorStatus", value=doorStateNames[int(state)])
#                    self.logger.debug(u'Created New Switch Device: %s (%s)' % (newdev.name, newdev.address))

    def getDeviceName(self, doorID):

        url =  self.service + '/Device/getDeviceAttribute?appId=' + self.appID + '&securityToken=' + self.securityToken + '&devId=' + doorID + '&name=desc'
        try:
            response = requests.get(url)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"getDeviceName: RequestException: " + str(err))
            return ""

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"getDeviceName: Bad return code: " + data['ErrorMessage'])
            return ""

        return data['AttributeValue']

    def getDeviceState(self, doorID):

        url =  self.service + '/Device/getDeviceAttribute?appId=' + self.appID + '&securityToken=' + self.securityToken + '&devId=' + doorID + '&name=doorstate'
        try:
            response = requests.get(url)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"getDeviceState: RequestException: " + str(err))
            return 0

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"getDeviceState: Bad return code: " + data['ErrorMessage'])
            return 0
        return int(data['AttributeValue'])

    ########################################

    def changeDeviceAction(self, pluginAction):

        if pluginAction != None:
            myqDevice = indigo.devices[pluginAction.deviceId]
            myqActionId = pluginAction.pluginTypeId
            if myqActionId == "openDoor":
                self.changeDevice(myqDevice, kDoorOpen)
            elif myqActionId == "closeDoor":
                self.changeDevice(myqDevice, kDoorClosed)
            elif myqActionId == "switchOn":
                self.changeDevice(myqDevice, kSwitchOn)
            elif myqActionId == "switchOff":
                self.changeDevice(myqDevice, kSwitchOff)
            else:
                self.logger.debug(u"changeDeviceAction, unknown myqActionId = %s" % myqActionId)

    def changeDevice(self, device, state):
        self.logger.debug(u"changeDevice: %s, state = %d" % (device.name, state))

        self.myqLogin()

        payload = {
           'ApplicationId': self.appID,
           'AttributeName': 'desireddoorstate',
           'DeviceId': device.address,
           'AttributeValue': state,
           'SecurityToken': self.securityToken
           }
        url = self.service + '/api/deviceattribute/putdeviceattribute'
        try:
            response = requests.put(url, data=payload)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"changeDevice: RequestException: " + str(err))
            return

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"changeDevice: Bad return code: " + data['ErrorMessage'])

        # schedule an update to check on the movement
        self.next_status_check = time.time() + 30.0