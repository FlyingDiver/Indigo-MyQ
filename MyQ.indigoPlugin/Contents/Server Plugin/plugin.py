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

doorStateNames = ["Unknown", "Open", "Closed", "Stopped", "Opening", "Closing", "Unknown", "Disconnected"]

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

    def actionControlDevice(self, action, dev):

        if action.deviceAction == indigo.kDeviceAction.Unlock:
            self.logger.debug(u"actionControlDevice: \"%s\" Unlock" % dev.name)
            self.changeDevice(dev, kDoorOpen)

        elif action.deviceAction == indigo.kDeviceAction.Lock:
            self.logger.debug(u"actionControlDevice: \"%s\" Lock" % dev.name)
            self.changeDevice(dev, kDoorClosed)

        elif action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.logger.debug(u"actionControlDevice: \"%s\" On" % dev.name)
            self.changeDevice(dev, kDoorOpen)

        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.logger.debug(u"actionControlDevice: \"%s\" Off" % dev.name)
            self.changeDevice(dev, kDoorClosed)

        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            self.logger.debug(u"actionControlDevice: \"%s\" Toggle" % dev.name)
            if dev.isOn:
                self.changeDevice(dev, kDoorClosed)
            else:
                self.changeDevice(dev, kDoorOpen)

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.debug(u"actionControlDevice: \"%s\" Request Status" % dev.name)
            self.getDevices()

    ########################################


    def myqLogin(self):

        self.username = self.pluginPrefs.get('myqLogin', None)
        self.password = self.pluginPrefs.get('myqPassword', None)
        self.brand = self.pluginPrefs.get('openerBrand', None)
        if (self.brand):
            self.service = self.apiData[self.brand]["service"]
            self.appID = self.apiData[self.brand]["appID"]

        payload = {'appId': self.appID, 'securityToken': 'null', 'username': self.username, 'password': self.password, 'culture': 'en'}
        login_url = self.service + '/Membership/ValidateUserWithCulture'
        headers = {'User-Agent': userAgent}

        try:
            response = requests.get(login_url, params=payload, headers=headers)
            self.logger.debug(u"myqLogin: response = " + str(response))
            self.logger.debug(u"myqLogin: content = " + str(response.text))
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
        self.logger.debug(u"myqLogin: Success, Brand = %s, SecurityToken = %s" % (data[u'BrandName'], self.securityToken))

    ########################################

    def getDevices(self):

        self.myqLogin()

        if not self.securityToken:
            return

        url =  self.service + '/api/UserDeviceDetails'
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
                        newState = doorStateNames[int(state)]
                        if dev.states["doorStatus"] != newState:
                            self.logger.info(u"MyQ Device %s is now %s" % (name, newState))
                        dev.updateStateOnServer(key="doorStatus", value=newState)
                        if state == 2:
                           dev.updateStateOnServer(key="onOffState", value=True)  # closed is True
                        else:
                            dev.updateStateOnServer(key="onOffState", value=False)   # anything other than closed is "unlocked"
                        break
                else:                           # Python syntax weirdness - this else belongs to the for loop!

                    # New MyQ device found, create it and set current state

                    newdev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                        address=myqID,
                        description = "Opener Device auto-created by MyQ plugin from gateway information",
                        deviceTypeId='myqOpener',
                        name=name)
                    newdev.updateStateOnServer(key="doorStatus", value=doorStateNames[int(state)])
                    if state == 2:
                        dev.updateStateOnServer(key="onOffState", value=True)
                    else:
                        dev.updateStateOnServer(key="onOffState", value=False)
                    self.logger.debug(u'Created New Opener Device: %s (%s)' % (newdev.name, newdev.address))


    def getDeviceName(self, doorID):

        url =  self.service + '/Device/getDeviceAttribute'
        params = {'appId': self.appID, 'securityToken': self.securityToken, 'devId': doorID, 'name':'desc'}
        headers = {'User-Agent': userAgent}
        try:
            response = requests.get(url, params=params, headers=headers)
        except requests.exceptions.RequestException as err:
            self.logger.debug(u"getDeviceName: RequestException: " + str(err))
            return ""

        data = response.json()
        if data['ReturnCode'] != '0':
            self.logger.debug(u"getDeviceName: Bad return code: " + data['ErrorMessage'])
            return ""

        return data['AttributeValue']

    def getDeviceState(self, doorID):

        url =  self.service + '/Device/getDeviceAttribute'
        params = {'appID': self.appID, 'securityToken': self.securityToken, 'devId': doorID, 'name':'doorstate'}
        headers = {'User-Agent': userAgent}
        try:
            response = requests.get(url, params=params, headers=headers)
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
        self.next_status_check = time.time() + 30.0

