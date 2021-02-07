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

            elif cmd == 'covers':
                if len(api.covers) != 0:
                    for device_id in api.covers:
                        device = api.devices[device_id]
                        data = {
                            'msg': 'device', 
                            'id': device_id, 
                            'name': device.name, 
                            'state': device.state, 
                            'online': device.online, 
                            'device_family': device.device_family, 
                            'device_platform': device.device_platform,
                            'device_type': device.device_type,
                        }
                        msg_write(json.dumps(data))

            elif cmd == 'lamps':
                if len(api.lamps) != 0:
                    for device_id in api.lamps:
                        device = api.devices[device_id]
                        data = {
                            'msg': 'device', 
                            'id': device_id, 
                            'name': device.name, 
                            'state': device.state, 
                            'online': device.online, 
                            'device_family': device.device_family, 
                            'device_platform': device.device_platform,
                            'device_type': device.device_type,
                        }
                        msg_write(json.dumps(data))

            elif cmd == 'gateways':
                if len(api.gateways) != 0:
                    for device_id in api.gateways:
                        device = api.devices[device_id]
                        data = {
                            'msg': 'device', 
                            'id': device_id, 
                            'name': device.name, 
                            'state': device.state, 
                            'online': device.online, 
                            'device_family': device.device_family, 
                            'device_platform': device.device_platform,
                            'device_type': device.device_type,
                        }
                        msg_write(json.dumps(data))
                        
            elif cmd == 'open':
                device = api.devices[request['id']]
                
                if device.open_allowed:
                    if device.state == STATE_OPEN:
                        msg_write(json.dumps({'msg': 'status', 'status': f"Garage door {device.name} is already open"}))
                    else:
                        msg_write(json.dumps({'msg': 'status', 'status': f"Opening garage door {device.name}"}))
                        try:
                            if await device.open(wait_for_state=True):
                                msg_write(json.dumps({'msg': 'status', 'status': f"Garage door {device.name} has been opened."}))
                            else:
                                msg_write(json.dumps({'msg': 'status', 'status': f"Failed to open garage door {device.name}."}))
                        except MyQError as err:
                            msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to open {device.name}: {str(err)}"}))
                else:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Opening of garage door {device.name} is not allowed."}))
                    
            elif cmd == 'close':
                device = api.devices[request['id']]

                if device.close_allowed:
                    if device.state == STATE_CLOSED:
                        msg_write(json.dumps({'msg': 'status', 'status': f"Garage door {device.name} is already closed"}))
                    else:
                        msg_write(json.dumps({'msg': 'status', 'status': f"Closing garage door {device.name}"}))
                        try:
                            wait_task = await device.close(wait_for_state=False)
                        except MyQError as err:
                            msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to close {device.name}: {str(err)}"}))

                        msg_write(json.dumps({'msg': 'status', 'status': f"Device {device.name} is {device.state}"}))

                        if await wait_task:
                            msg_write(json.dumps({'msg': 'status', 'status': f"Garage door {device.name} has been closed."}))
                        else:
                            msg_write(json.dumps({'msg': 'status', 'status': f"Failed to close garage door {device.name}."}))




    
# actual start of the program
    
asyncio.run(main(sys.argv))
