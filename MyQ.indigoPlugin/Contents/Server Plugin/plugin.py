#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import time
import requests
import logging
import json

import asyncio
try:
    from pymyq import login
    from pymyq.errors import MyQError, RequestError
    from pymyq.__version__ import __version__
    from aiohttp import ClientSession
except ImportError:
    raise ImportError("'Required Python libraries missing.  Run 'pip3 install pymyq==3.1.5' in Terminal window, then reload plugin.")

if __version__ != "3.1.5":
    raise ImportError("'Wrong version of MyQ library installed.  Run 'pip3 install pymyq==3.1.5' in Terminal window, then reload plugin.")

kCurDevVersCount = 2  # current version of plugin devices

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

        self.logLevel = int(pluginPrefs.get("logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(self.logLevel)
        log_format = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s',
                                       datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(log_format)
        self.logger.debug(f"logLevel = {self.logLevel}")

        self.needsUpdate = False
        self.triggers = {}
        self.myqOpeners = {}
        self.myqLamps = {}
        self.knownOpeners = {}
        self.knownLamps = {}
        self.device_info = {}

        self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
        self.logger.debug(f"statusFrequency = {self.statusFrequency}")
        self.next_status_check = time.time()

    def startup(self):  # noqa
        self.logger.info("Starting MyQ")
        indigo.devices.subscribeToChanges()  # Watch for changes to sensors associated with an opener

    def shutdown(self):  # noqa
        self.logger.info("Stopping MyQ")

    def runConcurrentThread(self):
        try:
            while True:
                if self.needsUpdate or (time.time() > self.next_status_check):
                    self.next_status_check = time.time() + self.statusFrequency
                    self.needsUpdate = False
                    asyncio.run(self.pymyq_update())
                self.sleep(1.0)
        except self.StopThread:
            self.logger.debug("Stopping runConcurrentThread")

    def deviceStartComm(self, device):

        self.logger.info(f"{device.name}: Starting {device.deviceTypeId} Device {device.id}")

        if device.deviceTypeId == 'myqOpener':

            myqID = device.pluginProps.get("myqID", None)
            if not device.address and myqID:
                newProps = device.pluginProps
                newProps["address"] = myqID
                device.replacePluginPropsOnServer(newProps)
                self.logger.debug(f"{device.name}: deviceStartComm: updated address to myqID {myqID}")

            instanceVers = int(device.pluginProps.get('devVersCount', 0))
            if instanceVers >= kCurDevVersCount:
                self.logger.debug(f"{device.name}: deviceStartComm: Device version is up to date ({instanceVers})")
            elif instanceVers < kCurDevVersCount:
                newProps = device.pluginProps
                newProps['IsLockSubType'] = True
                newProps["devVersCount"] = kCurDevVersCount
                device.replacePluginPropsOnServer(newProps)
                device.stateListOrDisplayStateIdChanged()
                self.logger.debug(
                    f"{device.name}: deviceStartComm: Updated to device version {kCurDevVersCount}, props = {newProps}")
            else:
                self.logger.error(f"{device.name}: deviceStartComm: Unknown device version: {instanceVers}")

            self.logger.debug(f"{device.name}: deviceStartComm: Adding device ({device.id}) to self.myqOpeners")
            assert device.id not in self.myqOpeners
            self.myqOpeners[device.id] = device
            self.needsUpdate = True

        elif device.deviceTypeId == 'myqLight':

            self.logger.debug(f"{device.name}: deviceStartComm: Adding device ({device.id}) to self.myqLamps")
            assert device.id not in self.myqLamps
            self.myqLamps[device.id] = device
            self.needsUpdate = True

    def deviceStopComm(self, device):

        self.logger.info(f"{device.name}: Stopping {device.deviceTypeId} Device {device.id}")

        if device.deviceTypeId == 'myqOpener':
            self.logger.debug(f"{device.name}: deviceStopComm: Removing device ({device.id}) from self.myqOpeners")
            assert device.id in self.myqOpeners
            del self.myqOpeners[device.id]

        elif device.deviceTypeId == 'myqLight':
            self.logger.debug(f"{device.name}: deviceStopComm: Removing device ({device.id}) from self.myqLamps")
            assert device.id in self.myqLamps
            del self.myqLamps[device.id]

    def triggerStartProcessing(self, trigger):
        self.logger.debug(f"Adding Trigger {trigger.name} ({trigger.id}) - {trigger.pluginTypeId}")
        assert trigger.id not in self.triggers
        self.triggers[trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug(f"Removing Trigger {trigger.name} ({trigger.id})")
        assert trigger.id in self.triggers
        del self.triggers[trigger.id]

    def triggerCheck(self, device):
        try:
            sensor = indigo.devices[int(device.pluginProps["sensor"])]
        except (Exception,):
            self.logger.debug(f"Skipping triggers, no linked sensor for MyQ device {device.name}")
            return

        for triggerId, trigger in sorted(self.triggers.items()):
            self.logger.debug(f"Checking Trigger {trigger.name} ({trigger.id}), Type: {trigger.pluginTypeId}")
            if isinstance(sensor, indigo.SensorDevice):
                sensor_state = sensor.onState
            elif isinstance(sensor, indigo.MultiIODevice):
                sensor_state = not sensor.states[
                    "binaryInput1"]  # I/O devices are opposite from sensors in terms of the state binary
            else:
                sensor_state = None
            if device.onState == sensor_state:  # these values are supposed to be opposite due to difference between sensor and lock devices
                indigo.trigger.execute(trigger)  # so execute the out of sync trigger when they're not opposite

    ########################################
    # Menu Methods
    ########################################

    def requestUpdate(self):
        self.needsUpdate = True
        return True

    def menuDumpMyQ(self):
        self.logger.info(
            f"MyQ Devices:\n{json.dumps(self.device_info, sort_keys=True, indent=4, separators=(',', ': '))}")
        return True

    ########################################
    # ConfigUI methods
    ########################################

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(f"validateDeviceConfigUi, valuesDict = {valuesDict}")
        errorsDict = indigo.Dict()

        if not valuesDict['address']:
            errorsDict['address'] = "Invalid Device"
            self.logger.warning(f"validateDeviceConfigUi: invalid device ID")

        if len(errorsDict) > 0:
            return False, valuesDict, errorsDict
        return True, valuesDict

    def validatePrefsConfigUi(self, valuesDict):
        self.logger.debug("validatePrefsConfigUi called")
        errorDict = indigo.Dict()

        try:
            self.logLevel = int(valuesDict[u"logLevel"])
        except (Exception,):
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
            return False, valuesDict, errorDict

        return True, valuesDict

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            try:
                self.logLevel = int(valuesDict[u"logLevel"])
            except (Exception,):
                self.logLevel = logging.INFO
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(f"logLevel = {self.logLevel}")

            self.statusFrequency = float(self.pluginPrefs.get('statusFrequency', "10")) * 60.0
            self.logger.debug(f"statusFrequency = {self.statusFrequency}")
            self.next_status_check = time.time() + self.statusFrequency

    def availableDeviceList(self, dev_filter="", valuesDict=None, typeId="", targetId=0):

        in_use = []
        retList = []

        if dev_filter == "garagedoor":
            for dev in indigo.devices.iter(filter="self.myqOpener"):
                in_use.append(dev.address)

            for myqID, myqName in self.knownOpeners.items():
                if myqID not in in_use:
                    retList.append((myqID, myqName))

            if targetId:
                try:
                    dev = indigo.devices[targetId]
                    retList.insert(0, (dev.pluginProps["address"], self.knownOpeners[dev.pluginProps["address"]]))
                except (Exception,):
                    pass

        elif dev_filter == "lamp":
            for dev in indigo.devices.iter(filter="self.myqLight"):
                in_use.append(dev.address)

            for myqID, myqName in self.knownLamps.items():
                if myqID not in in_use:
                    retList.append((myqID, myqName))

            if targetId:
                try:
                    dev = indigo.devices[targetId]
                    retList.insert(0, (dev.pluginProps["address"], self.knownLamps[dev.pluginProps["address"]]))
                except (Exception,):
                    pass

        self.logger.debug(f"availableDeviceList for {dev_filter}: retList = {retList}")
        return retList

    ################################################################################
    #
    # delegate methods for indigo.devices.subscribeToChanges()
    #
    ################################################################################

    def deviceDeleted(self, dev):
        indigo.PluginBase.deviceDeleted(self, dev)
        self.logger.debug(f"deviceDeleted: {dev.name} ")

        for myqDeviceId, myqDevice in sorted(self.myqOpeners.items()):
            try:
                sensorDev = myqDevice.pluginProps["sensor"]
            except (Exception,):
                return

            try:
                sensorID = int(sensorDev)
            except (Exception,):
                return

            if dev.id == sensorID:
                self.logger.info(f"A device ({dev.name}) that was associated with a MyQ device has been deleted.")
                newProps = myqDevice.pluginProps
                newProps["sensor"] = ""
                myqDevice.replacePluginPropsOnServer(newProps)

    def deviceUpdated(self, origDev, newDev):
        indigo.PluginBase.deviceUpdated(self, origDev, newDev)

        for myqDeviceId, myqDevice in sorted(self.myqOpeners.items()):
            try:
                sensorDev = int(myqDevice.pluginProps["sensor"])
            except (Exception,):
                pass
            else:
                if origDev.id == sensorDev:
                    if isinstance(newDev, indigo.SensorDevice):
                        old_sensor_state = origDev.onState
                        sensor_state = newDev.onState
                    elif isinstance(newDev, indigo.MultiIODevice):
                        old_sensor_state = not origDev.states[
                            "binaryInput1"]  # I/O devices are opposite from sensors in terms of the state binary
                        sensor_state = not newDev.states["binaryInput1"]
                    else:
                        self.logger.error(f"deviceUpdated: unknown device type for {origDev.name}")
                        return

                    if old_sensor_state == sensor_state:
                        self.logger.debug(f"deviceUpdated: {origDev.name} has not changed")
                        return

                    self.logger.debug(f"deviceUpdated: {origDev.name} has changed state: {sensor_state}")
                    # sensor "On" means the door's open, which is False for lock type devices (unlocked)
                    # sensor "Off" means the door's closed, which is True for lock type devices (locked)
                    if sensor_state:
                        myqDevice.updateStateOnServer(key="onOffState", value=False)
                    else:
                        myqDevice.updateStateOnServer(key="onOffState", value=True)
                    self.triggerCheck(myqDevice)

    ########################################

    def actionControlDevice(self, action, dev):

        if action.deviceAction == indigo.kDeviceAction.Unlock:
            self.logger.debug(f"actionControlDevice: Unlock {dev.name}")
            asyncio.run(self.pymyq_open(dev.address))

        elif action.deviceAction == indigo.kDeviceAction.Lock:
            self.logger.debug(f"actionControlDevice: Lock {dev.name}")
            asyncio.run(self.pymyq_close(dev.address))

        elif action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.logger.debug(f"actionControlDevice: TurnOn {dev.name}")
            asyncio.run(self.pymyq_turnon(dev.address))

        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.logger.debug(f"actionControlDevice: TurnOff {dev.name}")
            asyncio.run(self.pymyq_turnoff(dev.address))

        elif action.deviceAction == indigo.kDeviceAction.RequestStatus:
            self.logger.debug("actionControlDevice: Request Status")
            asyncio.get_event_loop().run(self.pymyq_update())

        else:
            self.logger.error(f"actionControlDevice: Unsupported action requested: {action} for {dev.name}")

    ########################################

    def changeDeviceAction(self, pluginAction):
        self.logger.debug(f"changeDeviceAction, deviceId = {pluginAction.deviceId}, actionId = {pluginAction.pluginTypeId}")

        if pluginAction is not None:
            myqDevice = indigo.devices[pluginAction.deviceId]
            myqActionId = pluginAction.pluginTypeId
            if myqActionId == "openDoor":
                asyncio.run(self.pymyq_open(myqDevice.address))
            elif myqActionId == "closeDoor":
                asyncio.run(self.pymyq_close(myqDevice.address))
            else:
                self.logger.debug(f"changeDeviceAction, unknown myqActionId = {myqActionId}")
                return

    ################################################################################

    async def pymyq_update(self):
        async with ClientSession() as web_session:
            try:
                api = await login(self.pluginPrefs['myqLogin'], self.pluginPrefs['myqPassword'], web_session)
            except MyQError as err:
                self.logger.warning(f"Error logging into MyQ server: {err}")
                return

            await api.update_device_info()

            for device_id in api.devices:
                device_json = api.devices[device_id].device_json
                name = device_json['name']
                myqID = device_json['serial_number']
                family = device_json['device_family']
                self.logger.debug(f"pymyq_update: got {name} - {family} ({myqID})")
                self.device_info[myqID] = device_json

                if family == 'garagedoor':

                    state = device_json['state']['door_state']
                    self.logger.debug(f"pymyq_read: door state = {state}")

                    if myqID not in self.knownOpeners:
                        self.knownOpeners[myqID] = name

                    for dev in indigo.devices.iter(filter="self.myqOpener"):
                        self.logger.debug(f'Checking Opener Device: {dev.name} ({dev.address}) against {myqID}')
                        if dev.address == myqID:
                            dev.updateStateOnServer(key="doorStatus", value=state)
                            if state == STATE_CLOSED:
                                dev.updateStateOnServer(key="onOffState", value=True)  # closed is True (Locked)
                            else:
                                dev.updateStateOnServer(key="onOffState",
                                                        value=False)  # anything other than closed is "Unlocked"
                            self.triggerCheck(dev)
                            break

                elif family == 'lamp':
                    state = device_json['state']['lamp_state']
                    self.logger.debug(f"pymyq_read: lamp state = {state}")

                    if myqID not in self.knownLamps:
                        self.knownLamps[myqID] = name

                    for dev in indigo.devices.iter(filter="self.myqLight"):
                        self.logger.debug(
                            f"Checking Lamp Device: {dev.name} ({dev.address}) against {myqID}")
                        if dev.address == myqID:
                            if state == "on":
                                dev.updateStateOnServer(key="onOffState", value=True)
                            else:
                                dev.updateStateOnServer(key="onOffState", value=False)
                            break

    async def pymyq_open(self, myqid):
        async with ClientSession() as web_session:
            try:
                api = await login(self.pluginPrefs['myqLogin'], self.pluginPrefs['myqPassword'], web_session)
            except MyQError as err:
                self.logger.warning(f"Error logging into MyQ server: {err}")
                return

            device = api.devices[myqid]
            if not device.open_allowed:
                self.logger.warning(f"Opening of '{device.name}' is not allowed.")
                return

            if device.state == STATE_OPEN:
                self.logger.info(f"'{device.name}' is already open.")
                return

            try:
                wait_task = await device.open(wait_for_state=False)
            except MyQError as err:
                self.logger.error(f"Error trying to open '{device.name}': {err}")
                return

            if not await wait_task:
                self.logger.warning(f"Failed to open '{device.name}'.")
            self.needsUpdate = True
            return

    async def pymyq_close(self, myqid):
        async with ClientSession() as web_session:
            try:
                api = await login(self.pluginPrefs['myqLogin'], self.pluginPrefs['myqPassword'], web_session)
            except MyQError as err:
                self.logger.warning(f"Error logging into MyQ server: {err}")
                return

            device = api.devices[myqid]
            if not device.close_allowed:
                self.logger.warning(f"Closing of '{device.name}' is not allowed.")
                return

            if device.state == STATE_CLOSED:
                self.logger.info(f"'{device.name}' is already closed.")
                return

            try:
                wait_task = await device.close(wait_for_state=False)
            except MyQError as err:
                self.logger.error(f"Error trying to close '{device.name}': {err}")
                return

            if not await wait_task:
                self.logger.warning(f"Failed to close '{device.name}'.")
            self.needsUpdate = True
            return

    async def pymyq_turnon(self, myqid):
        async with ClientSession() as web_session:
            try:
                api = await login(self.pluginPrefs['myqLogin'], self.pluginPrefs['myqPassword'], web_session)
            except MyQError as err:
                self.logger.warning(f"Error logging into MyQ server: {err}")
                return

            device = api.devices[myqid]
            try:
                wait_task = await device.turnon(wait_for_state=False)
            except MyQError as err:
                self.logger.error(f"Error trying to turn on '{device.name}': {err}")
                return

            if not await wait_task:
                self.logger.warning(f"Failed to turn on '{device.name}'.")
            self.needsUpdate = True
            return

    async def pymyq_turnoff(self, myqid):
        async with ClientSession() as web_session:
            try:
                api = await login(self.pluginPrefs['myqLogin'], self.pluginPrefs['myqPassword'], web_session)
            except MyQError as err:
                self.logger.warning(f"Error logging into MyQ server: {err}")
                return

            device = api.devices[myqid]
            try:
                wait_task = await device.turnoff(wait_for_state=False)
            except MyQError as err:
                self.logger.error(f"Error trying to turn off '{device.name}': {err}")
                return

            if not await wait_task:
                self.logger.warning(f"Failed to turn off '{device.name}'.")
            self.needsUpdate = True
            return
