#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import time
import requests
import logging
import json

from subprocess import Popen, PIPE
from threading import Thread


kCurDevVersCount = 2       # current version of plugin devices

STATE_CLOSED = "closed"
STATE_CLOSING = "closing"
STATE_OPEN = "open"
STATE_OPENING = "opening"
STATE_STOPPED = "stopped"
STATE_TRANSITION = "transition"
STATE_AUTOREVERSE = "autoreverse"
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
        self.needsUpdate = False
        self.triggers = { }

        self.myqOpeners = {}
        self.myqLamps = {}
        
        self.knownOpeners = {}
        self.knownLamps = {}
        
        self.device_info = {}
        
        self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
        self.logger.debug(u"statusFrequency = {}".format(self.statusFrequency))
        self.next_status_check = time.time() + 10.0     # wait for subprocess to start up

        # Watch for changes to sensors associated with an opener
        indigo.devices.subscribeToChanges()

        # Start up the pymyq wrapper task            
        self.pymyq = Popen(['/usr/bin/python3', './py3myq/wrapper.py', self.pluginPrefs['myqLogin'], self.pluginPrefs['myqPassword']], 
                                stdin=PIPE, stdout=PIPE, close_fds=True, bufsize=1, universal_newlines=True)
                                
        # start up the reader thread        
        self.read_thread = Thread(target=self.pymyq_read)
        self.read_thread.daemon = True
        self.read_thread.start()
        
    def shutdown(self):
        indigo.server.log(u"Stopping MyQ")
        self.pymyq.terminate()

    def runConcurrentThread(self):

        try:
            while True:

                if self.needsUpdate or (time.time() > self.next_status_check):
                    self.next_status_check = time.time() + self.statusFrequency
                    self.needsUpdate = False
                    self.requestUpdate()     # only do this device type for now
                                    
                self.sleep(1.0)

        except self.StopThread:
            pass

################################################################################

    def pymyq_write(self, msg):
        jsonMsg = json.dumps(msg)
        self.logger.threaddebug(u"Send pymyq message: {}".format(jsonMsg))
        self.pymyq.stdin.write(u"{}\n".format(jsonMsg))


    def pymyq_read(self):
        while True:
            msg = self.pymyq.stdout.readline()
            self.logger.threaddebug(u"Received pymyq message: {}".format(msg.rstrip()))
            
            data = json.loads(msg)
            if data['msg'] == 'status':
                self.logger.info(data['status'])  
                
            elif data['msg'] == 'error':
                self.logger.error(data['error'])  
                
            elif data['msg'] == 'account':
                self.logger.debug(u"pymyq_read: account ID = {}, name = {}".format(data['id'], data['name']))
            
            elif data['msg'] == 'device':            
                name = data['props']['name']
                myqID = data['props']['serial_number']
                family = data['props']['device_family']
                self.logger.debug(u"pymyq_read: device ID = {}, name = {}, family = {}".format(myqID, name, family))
            
                self.device_info[myqID] = data['props']
                
                if family == u'garagedoor':

                    state = data['props']['state']['door_state']
                    self.logger.debug(u"pymyq_read: door state = {}".format(state))

                    if not myqID in self.knownOpeners:
                        self.knownOpeners[myqID] = name
                    
                    for dev in indigo.devices.iter(filter="self"):
                        self.logger.debug(u'Checking Opener Device: {} ({}) against {}'.format(dev.name, dev.address, myqID))
                        if dev.address == myqID:
                            dev.updateStateOnServer(key="doorStatus", value=state)
                            if state == STATE_CLOSED:
                               dev.updateStateOnServer(key="onOffState", value=True)  # closed is True (Locked)
                            else:
                                dev.updateStateOnServer(key="onOffState", value=False)   # anything other than closed is "Unlocked"
                            self.triggerCheck(dev)
                            break                    

                elif family == u'lamp':
                    state = data['props']['state']['lamp_state']
                    self.logger.debug(u"pymyq_read: lamp state = {}".format(state))

                    if not myqID in self.knownLamps:
                        self.knownLamps[myqID] = name
                    
               
 
    def requestUpdate(self):
        cmd = {'cmd': 'accounts'} 
        self.pymyq_write(cmd)
        cmd = {'cmd': 'devices'} 
        self.pymyq_write(cmd)
    
      
################################################################################



    def deviceStartComm(self, device):

        myqID = device.pluginProps.get("myqID", None)
        if myqID != device.address:
            newProps = device.pluginProps
            newProps["address"] = myqID
            device.replacePluginPropsOnServer(newProps)
            self.logger.debug(u"{}: deviceStartComm: updated address to myqID {}".format(device.name, myqID))

        instanceVers = int(device.pluginProps.get('devVersCount', 0))
        if instanceVers >= kCurDevVersCount:
            self.logger.debug(u"{}: deviceStartComm: Device version is up to date ({})".format(device.name, instanceVers))
        elif instanceVers < kCurDevVersCount:
            newProps = device.pluginProps
            newProps['IsLockSubType'] = True
            newProps["devVersCount"] = kCurDevVersCount
            device.replacePluginPropsOnServer(newProps)
            device.stateListOrDisplayStateIdChanged()
            self.logger.debug(u"{}: deviceStartComm: Updated to device version {}, props = {}".format(device.name, kCurDevVersCount, newProps))
        else:
            self.logger.error(u"{}: deviceStartComm: Unknown device version: {}".format(device.name, instanceVers))
        
        self.logger.debug("{}: deviceStartComm: Adding device ({}) to MyQ device list".format(device.name, device.id))
        assert device.id not in self.myqOpeners
        self.myqOpeners[device.id] = device
        self.needsUpdate = True
        
    def deviceStopComm(self, device):
        self.logger.debug("{}: deviceStopComm: Removing device ({}) from MyQ device list".format(device.name, device.id))
        assert device.id in self.myqOpeners
        del self.myqOpeners[device.id]

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        valuesDict['myqID'] = valuesDict['address']
        return (True, valuesDict)


    def triggerStartProcessing(self, trigger):
        self.logger.debug("Adding Trigger {} ({}) - {}".format(trigger.name, trigger.id, trigger.pluginTypeId))
        assert trigger.id not in self.triggers
        self.triggers[trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug("Removing Trigger {} ({})".format(trigger.name, trigger.id))
        assert trigger.id in self.triggers
        del self.triggers[trigger.id]

    def triggerCheck(self, device):
        try:
            sensor = indigo.devices[int(device.pluginProps["sensor"])]
        except:
            self.logger.debug("Skipping triggers, no linked sensor for MyQ device %s" % (device.name))
            return

        for triggerId, trigger in sorted(self.triggers.iteritems()):
            self.logger.debug("Checking Trigger {} ({}), Type: {}".format(trigger.name, trigger.id, trigger.pluginTypeId))
            if isinstance(sensor, indigo.SensorDevice):
                sensor_state = sensor.onState
            elif isinstance(sensor, indigo.MultiIODevice):
                sensor_state = not sensor.states["binaryInput1"] # I/O devices are opposite from sensors in terms of the state binary
            
            self.logger.debug("\tmyqDoorSync:  {} is {}, linked sensor {} is {}".format(device.name, str(device.onState), sensor.name, str(sensor_state)))

            if device.onState == sensor_state:        # these values are supposed to be opposite due to difference between sensor and lock devices
                indigo.trigger.execute(trigger)         # so execute the out of sync trigger when they're not opposite


    ########################################
    # Menu Methods
    ########################################

    def menuDumpMyQ(self):
        self.logger.info(u"MyQ Devices:\n{}".format(json.dumps(self.device_info, sort_keys=True, indent=4, separators=(',', ': '))))
        return True
        

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
            self.logger.debug(u"statusFrequency = {}".format(self.statusFrequency))
            self.next_status_check = time.time() + self.statusFrequency


    def availableDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):

        in_use =[]
        for dev in indigo.devices.iter(filter="self.myqOpener"):
            in_use.append(dev.address)

        retList =[]
        for myqID, myqName in self.knownOpeners.iteritems():
            if myqID not in in_use:
                retList.append((myqID, myqName))

        if targetId:
            try:
                dev = indigo.devices[targetId]
                retList.insert(0, (dev.pluginProps["address"], self.knownOpeners[dev.pluginProps["address"]]))
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

        for myqDeviceId, myqDevice in sorted(self.myqOpeners.iteritems()):
            try:
                sensorDev = myqDevice.pluginProps["sensor"]
            except:
                return
            
            try:
                sensorID = int(sensorDev)
            except:
                return
                
            if dev.id == sensorID:
                self.logger.info(u"A device ({}) that was associated with a MyQ device has been deleted.".format(dev.name))
                newProps = myqDevice.pluginProps
                newProps["sensor"] = ""
                myqDevice.replacePluginPropsOnServer(newProps)


    def deviceUpdated(self, origDev, newDev):
        indigo.PluginBase.deviceUpdated(self, origDev, newDev)

        for myqDeviceId, myqDevice in sorted(self.myqOpeners.iteritems()):
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
                        self.logger.error(u"deviceUpdated: unknown device type for {}".format(origDev.name))
                        
                    if old_sensor_state == sensor_state:
                        self.logger.debug(u"deviceUpdated: {} has not changed".format(origDev.name))
                        return

                    self.logger.debug(u"deviceUpdated: {} has changed state: {}".format(origDev.name, sensor_state))
                    if sensor_state:
                        myqDevice.updateStateOnServer(key="onOffState", value=False)   # sensor "On" means the door's open, which is False for lock type devices (unlocked)
                    else:
                        myqDevice.updateStateOnServer(key="onOffState", value=True)   # sensor "Off" means the door's closed, which is True for lock type devices (locked)
                    self.triggerCheck(myqDevice)

    ########################################

    def actionControlDevice(self, action, dev):

        if action.deviceAction == indigo.kDeviceAction.Unlock:
            self.logger.debug(u"actionControlDevice: Unlock {}".format(dev.name))
            cmd = {'cmd': 'open', 'id': dev.address} 
            self.pymyq_write(cmd)

        elif action.deviceAction == indigo.kDeviceAction.Lock:
            self.logger.debug(u"actionControlDevice: Lock {}".format(dev.name))
            cmd = {'cmd': 'close', 'id': dev.address} 
            self.pymyq_write(cmd)

        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.logger.debug(u"actionControlDevice: TurnOn {}".format(dev.name))
            cmd = {'cmd': 'turnon', 'id': dev.address} 
            self.pymyq_write(cmd)

        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.logger.debug(u"actionControlDevice: TurnOff {}".format(dev.name))
            cmd = {'cmd': 'turnoff', 'id': dev.address} 
            self.pymyq_write(cmd)

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.debug(u"actionControlDevice: Request Status")
            self.requestUpdate()

        else:
            self.logger.error(u"actionControlDevice: Unsupported action requested: {} for {}".format(action, dev.name))


    ########################################

    def changeDeviceAction(self, pluginAction):
        self.logger.debug(u"changeDeviceAction, deviceId = {}, actionId = {}".format(pluginAction.deviceId, pluginAction.pluginTypeId))

        if pluginAction != None:
            myqDevice = indigo.devices[pluginAction.deviceId]
            myqActionId = pluginAction.pluginTypeId
            if myqActionId == "openDoor":
                cmd = {'cmd': 'open', 'id': myqDevice.address} 
                self.pymyq_write(cmd)
            elif myqActionId == "closeDoor":
                cmd = {'cmd': 'close', 'id': myqDevice.address} 
                self.pymyq_write(cmd)
            else:
                self.logger.debug(u"changeDeviceAction, unknown myqActionId = {}".format(myqActionId))
                return

            # schedule an update to check on the movement
            self.next_status_check = time.time() + float(self.pluginPrefs.get('statusDelay', "30"))


        

