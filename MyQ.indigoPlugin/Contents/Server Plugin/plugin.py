#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
## Python to interface with MyQ garage doors.
## based on https://github.com/Einstein42/myq-garage
 
'''
The MIT License (MIT)

Copyright (c) 2016

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import sys
import time
import requests

from requests.auth import HTTPBasicAuth
from requests.utils import quote

from ghpu import GitHubPluginUpdater

kCurDevVersCount = 0		# current version of plugin devices			

kDoorClosed = 0
kDoorOpen 	= 1
kswitchOff	= 0
kswitchOn 	= 1

doorStateNames = ["Unknown", "Open", "Closed", "Stopped", "Opening", "Closing"]

################################################################################
class Plugin(indigo.PluginBase):
					
	########################################
	# Main Plugin methods
	########################################
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

		self.debug = self.pluginPrefs.get(u"showDebugInfo", False)
		self.debugLog(u"Debugging enabled")

		self.apiData = {
			"chamberlain" : { 	"service" : "https://myqexternal.myqdevice.com", 
								"appID" : "Vj8pQggXLhLy0WHahglCD4N1nAkkXQtGYpq2HrHD7H1nvmbT55KqtN6RSF4ILB%2fi" 
							},
			"craftsman" :	{ 	"service" : "https://craftexternal.myqdevice.com", 
								"appID" : "eU97d99kMG4t3STJZO/Mu2wt69yTQwM0WXZA5oZ74/ascQ2xQrLD/yjeVhEQccBZ" 
							},
			"liftmaster" : { 	"service" : "https://myqexternal.myqdevice.com", 
								"appID" : "Vj8pQggXLhLy0WHahglCD4N1nAkkXQtGYpq2HrHD7H1nvmbT55KqtN6RSF4ILB%2fi" 
							},
						}
						
		self.triggers = { }

	def __del__(self):
		indigo.PluginBase.__del__(self)

	def startup(self):
		indigo.server.log(u"Starting MyQ")
		
		self.updater = GitHubPluginUpdater(self)
		self.updateFrequency = self.pluginPrefs.get('updateFrequency', 24)
		if self.updateFrequency > 0:
			self.next_update_check = time.time() + float(self.pluginPrefs.get('updateFrequency', 24))

		self.statusFrequency = self.pluginPrefs.get('statusFrequency', 10)
		if self.statusFrequency > 0:
			self.next_status_check = time.time() + float(self.pluginPrefs.get('statusFrequency', 10))


	def shutdown(self):
		indigo.server.log(u"Shutting down MyQ")


	def runConcurrentThread(self):
		
		try:
			while True:
				
				if self.updateFrequency > 0:
					if time.time() > self.next_update_check:
						self.updater.checkForUpdate()
						self.next_update_check = time.time() + float(self.pluginPrefs.get('updateFrequency', 24)) * 60.0 * 60.0

				if self.statusFrequency > 0:
					if time.time() > self.next_status_check:
						self.getDevices()
						self.next_status_check = time.time() + float(self.pluginPrefs.get('statusFrequency', 10)) * 60.0

				self.sleep(1.0) 
								
		except self.stopThread:
			pass
							

	####################


	def triggerStartProcessing(self, trigger):
		self.debugLog("Adding Trigger %s (%d) - %s" % (trigger.name, trigger.id, trigger.pluginTypeId))
		assert trigger.id not in self.triggers
		self.triggers[trigger.id] = trigger
 
	def triggerStopProcessing(self, trigger):
		self.debugLog("Removing Trigger %s (%d)" % (trigger.name, trigger.id))
		assert trigger.id in self.triggers
		del self.triggers[trigger.id] 
		
	def triggerCheck(self, device):
		for triggerId, trigger in sorted(self.triggers.iteritems()):
			self.debugLog("\tChecking Trigger %s (%s), Type: %s" % (trigger.name, trigger.id, trigger.pluginTypeId))
			
	####################	


#	def deviceStartComm(self, device):
#		self.debugLog(u'Called deviceStartComm(self, device): %s (%s)' % (device.name, device.id))
						
#		instanceVers = int(device.pluginProps.get('devVersCount', 0))
#		self.debugLog(device.name + u": Device Current Version = " + str(instanceVers))

#		if instanceVers >= kCurDevVersCount:
#			self.debugLog(device.name + u": Device Version is up to date")
			
#		elif instanceVers < kCurDevVersCount:
#			newProps = device.pluginProps

#		else:
#			self.errorLog(u"Unknown device version: " + str(instanceVers) + " for device " + device.name)					
		
							
#	def deviceStopComm(self, device):
#		self.debugLog(u'Called deviceStopComm(self, device): %s (%s)' % (device.name, device.id))
		
 
	########################################
	# Menu Methods
	########################################

	def toggleDebugging(self):
		self.debug = not self.debug
		self.pluginPrefs["debugEnabled"] = self.debug
		indigo.server.log("Debug set to: " + str(self.debug))
		
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
		self.debugLog(u"validatePrefsConfigUi called")
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
			self.debug = valuesDict.get("showDebugInfo", False)
			if self.debug:
				self.debugLog(u"Debug logging enabled")
			else:
				self.debugLog(u"Debug logging disabled")
				

#	def validateDeviceConfigUi(self, valuesDict, typeId, devId):
#		self.debugLog(u'Called validateDeviceConfigUi, valuesDict = %s, typeId = %s, devId = %s' % (str(valuesDict), typeId, devId))
#		errorsDict = indigo.Dict()

#		if int(valuesDict["address"]) < 1:
#			errorDict['address'] = u"Invalid Device ID Number"
			
#		if len(errorsDict) > 0:
#			return (False, valuesDict, errorsDict)
#		return (True, valuesDict)


#	def validateActionConfigUi(self, valuesDict, typeId, devId):
#		self.debugLog(u'Called validateActionConfigUi, valuesDict = %s, typeId = %s, devId = %s' % (str(valuesDict), typeId, devId))
#		errorsDict = indigo.Dict()
#		try:
#			pass
#		except:
#			pass
#		if len(errorsDict) > 0:
#			return (False, valuesDict, errorsDict)
#		return (True, valuesDict)

	########################################
	
	def actionControlDimmerRelay(self, action, dev):
	
		if action.deviceAction == indigo.kDeviceAction.TurnOn:
			self.debugLog(u"actionControlDimmerRelay: \"%s\" On" % dev.name)
			self.changeDevice(dev, kDoorOpen)

		elif action.deviceAction == indigo.kDeviceAction.TurnOff:
			self.debugLog(u"actionControlDimmerRelay: \"%s\" Off" % dev.name)
			self.changeDevice(dev, kDoorClosed)
			
		elif action.deviceAction == indigo.kDeviceAction.Toggle:
			self.debugLog(u"actionControlDimmerRelay: \"%s\" Toggle" % dev.name)
			if dev.isOn:
				self.changeDevice(dev, kDoorClosed)
			else:	
				self.changeDevice(dev, kDoorOpen)

		elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
			self.debugLog(u"actionControlDimmerRelay: \"%s\" Request Status" % dev.name)
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
			self.debugLog(u"myqLogin: RequestException: " + str(err))
			return 
			             
		data = response.json()
		if data['ReturnCode'] != '0':
			self.debugLog(u"myqLogin: Bad return code: " + data['ErrorMessage'])
			return		
		
		self.securityToken = data['SecurityToken']
		self.debugLog(u"myqLogin: Success, Brand = %s, SecurityToken = %s" % (data[u'BrandName'], self.securityToken))
	
	########################################
	
	def getDevices(self):

		self.myqLogin()
			
		url =  self.service + '/api/UserDeviceDetails?appId=' + self.appID + '&securityToken=' + self.securityToken
		try:
			response = requests.get(url)
		except requests.exceptions.RequestException as err:
			self.debugLog(u"getDevices: RequestException: " + str(err))
			return 
			             
		data = response.json()
		if data['ReturnCode'] != '0':
			self.debugLog(u"getDevices: Bad return code: " + data['ErrorMessage'])
			return		

		self.debugLog(u"getDevices: %d Devices" % len(data['Devices']))

		for device in data['Devices']:
			self.debugLog(u"getDevices: MyQDeviceTypeId = %s, DeviceId = %s" % (device['MyQDeviceTypeId'], device['DeviceId']))
			
			if device['MyQDeviceTypeId'] == 2:			# MyQDeviceTypeId Gateway == 1, Doors == 2, Structure == 10, Thermostat == 11
				myqID = device['DeviceId']
				name = self.getDeviceName(myqID)
				state = self.getDeviceState(myqID)
				self.debugLog(u"getDevices: Opener = %s (%s), state = %i" % (name, myqID, state))
				
				# look for this opener device in the existing devices for this plugin.  If it's not there (by id), then create it
				
				iterator = indigo.devices.iter(filter="com.flyingdiver.indigoplugin.myq")
				for dev in iterator:
					if dev.address == myqID:
						dev.updateStateOnServer(key="doorStatus", value=doorStateNames[state])
						if state == 2:
							dev.updateStateOnServer(key="onOffState", value=False)	# closed is off
						else:
							dev.updateStateOnServer(key="onOffState", value=True)	# anything other than closed is "on"
						break
				else:							# Python syntax weirdness - this else belongs to the for loop!
					newdev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
    					address=myqID,
    					description = "Opener Device auto-created by MyQ plugin from gateway information",
    					deviceTypeId='myqOpener',
    					name=name)
					newdev.updateStateOnServer(key="doorStatus", value=doorStateNames[int(state)])
					self.debugLog(u'Created New Opener Device: %s (%s)' % (newdev.name, newdev.address))
		
			elif device['MyQDeviceTypeId'] == 3:			# Switch == 3?
				myqID = device['DeviceId']
				name = self.getDeviceName(myqID)
				state = self.getDeviceState(myqID)
				self.debugLog(u"getDevices: Switch = %s (%s), state = %i" % (name, myqID, state))
			
				# look for this opener device in the existing devices for this plugin.  If it's not there (by id), then create it
			
				iterator = indigo.devices.iter(self)
				for dev in iterator:
					if dev.address == myqID:
						break
				else:							# Python syntax weirdness - this else belongs to the for loop!
					newdev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
						address=myqID,
						description = "Switch Device auto-created by MyQ plugin from gateway information",
						deviceTypeId='myqSwitch',
						name=name)
#					newdev.updateStateOnServer(key="doorStatus", value=doorStateNames[int(state)])
					self.debugLog(u'Created New Switch Device: %s (%s)' % (newdev.name, newdev.address))

	def getDeviceName(self, doorID):

		url =  self.service + '/Device/getDeviceAttribute?appId=' + self.appID + '&securityToken=' + self.securityToken + '&devId=' + doorID + '&name=desc'
		try:
			response = requests.get(url)
		except requests.exceptions.RequestException as err:
			self.debugLog(u"getDeviceName: RequestException: " + str(err))
			return     

		data = response.json()
		if data['ReturnCode'] != '0':
			self.debugLog(u"getDeviceName: Bad return code: " + data['ErrorMessage'])
			return ""
			
		return data['AttributeValue']

	def getDeviceState(self, doorID):

		url =  self.service + '/Device/getDeviceAttribute?appId=' + self.appID + '&securityToken=' + self.securityToken + '&devId=' + doorID + '&name=doorstate'
		try:
			response = requests.get(url)
		except requests.exceptions.RequestException as err:
			self.debugLog(u"getDeviceState: RequestException: " + str(err))
			return              

		data = response.json()
		if data['ReturnCode'] != '0':
			self.debugLog(u"getDeviceState: Bad return code: " + data['ErrorMessage'])
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
				self.debugLog(u"changeDeviceAction, unknown myqActionId = %s" % myqActionId)
				
	def changeDevice(self, device, state):
		self.debugLog(u"changeDevice: %s, state = %d" % (device.name, state))

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
			self.debugLog(u"changeDevice: RequestException: " + str(err))
			return 
          
		data = response.json()
		if data['ReturnCode'] != '0':
			self.debugLog(u"changeDevice: Bad return code: " + data['ErrorMessage'])

		# schedule an update to check on the movement
		self.next_status_check = time.time() + 30.0