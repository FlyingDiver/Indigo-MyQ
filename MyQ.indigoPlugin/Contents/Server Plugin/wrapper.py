"""Python3 Wrapper for MyQ"""
import asyncio
import sys
import json

from aiohttp import ClientSession

from pymyq import login
from pymyq.errors import MyQError, RequestError


STATE_CLOSED = "closed"
STATE_CLOSING = "closing"
STATE_OPEN = "open"
STATE_OPENING = "opening"
STATE_STOPPED = "stopped"
STATE_TRANSITION = "transition"
STATE_AUTOREVERSE = "autoreverse"
STATE_UNKNOWN = "unknown"

def msg_write(msg):
    sys.stdout.write(u"{}\n".format(msg))
    sys.stdout.flush()

async def main(args) -> None:

    async with ClientSession() as websession:
        try:
            api = await login(sys.argv[1], sys.argv[2], websession)

        except MyQError as err:
            msg_write(json.dumps({'msg': 'status', 'status': "Login Error"}))
            msg_write(json.dumps({'msg': 'error', 'error': err.args}))
            return

        msg_write(json.dumps({'msg': 'status', 'status': "Login Complete"}))

        # process requests from the plugin
                      
        for line in sys.stdin:

            request = json.loads(line.rstrip())
            msg_write(json.dumps({'msg': 'echo', 'request': request}))
            cmd = request['cmd']
            
            if cmd == 'stop':
                break

            elif cmd == 'accounts':
                for account in api.accounts:
                    msg_write(json.dumps({'msg': 'account', 'id': account, 'name': api.accounts[account]}))

            elif cmd == 'devices':
                for device_id in api.devices:
                    device = api.devices[device_id]
                    msg_write(json.dumps({'msg': 'device', 'id': device_id, 'props':device.device_json}))
                        
            elif cmd == 'open':
                device = api.devices[request['id']]
                
                if not device.open_allowed:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Opening of garage door {device.name} is not allowed."}))
                    return
                    
                if device.state == STATE_OPEN:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Garage door {device.name} is already open"}))
                    return
                    
                try:
                    wait_task = await device.open(wait_for_state=False)
                except MyQError as err:
                    msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to open {device.name}: {str(err)}"}))
                    device = api.devices[device.device_id]
                    msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))
                    return
                         
                msg_write(json.dumps({'msg': 'status', 'status': f"Device {device.name} is {device.state}"}))
               
                if not await wait_task:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Failed to close garage door {device.name}."}))
                device = api.devices[device.device_id]
                msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))
                    
            elif cmd == 'close':
                device = api.devices[request['id']]

                if not device.close_allowed:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Closing of garage door {device.name} is not allowed."}))
                    return
                    
                if device.state == STATE_CLOSED:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Garage door {device.name} is already closed"}))
                    return
                    
                try:
                    wait_task = await device.close(wait_for_state=False)
                except MyQError as err:
                    msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to close {device.name}: {str(err)}"}))
                    device = api.devices[device.device_id]
                    msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))
                    return
                    
                msg_write(json.dumps({'msg': 'status', 'status': f"Device {device.name} is {device.state}"}))

                if not await wait_task:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Failed to close garage door {device.name}."}))
                device = api.devices[device.device_id]
                msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))


            elif cmd == 'turnon':
                device = api.devices[request['id']]
                msg_write(json.dumps({'msg': 'status', 'status': f"Turning lamp {device.name} on"}))
                
                try:
                    wait_task = await device.turnon(wait_for_state=False)
                except MyQError as err:
                    msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to turn on {device.name}: {str(err)}"}))
                    device = api.devices[device.device_id]
                    msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))
                         
                msg_write(json.dumps({'msg': 'status', 'status': f"Device {device.name} is {device.state}"}))

                if not await wait_task:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Failed to turn on lamp {device.name}."}))
                device = api.devices[device.device_id]
                msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))

                     
            elif cmd == 'turnoff':
                device = api.devices[request['id']]
                msg_write(json.dumps({'msg': 'status', 'status': f"Turning lamp {device.name} off"}))
                try:
                    wait_task = await device.turnoff(wait_for_state=False)
                except RequestError as err:
                    msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to turn off {device.name}: {str(err)}"}))
                    device = api.devices[device.device_id]
                    msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))

                msg_write(json.dumps({'msg': 'status', 'status': f"Device {device.name} is {device.state}"}))

                if not await wait_task:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Failed to turn off lamp {device.name}."}))
                device = api.devices[device.device_id]
                msg_write(json.dumps({'msg': 'device', 'id': device.device_id, 'props':device.device_json}))

    
# actual start of the program
    
asyncio.run(main(sys.argv))
