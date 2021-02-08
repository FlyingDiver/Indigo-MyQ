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
                else:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Closing of garage door {device.name} is not allowed."}))


            elif cmd == 'turnon':
                device = api.devices[request['id']]
                try:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Turning lamp {device.name} on"}))
                    await device.turnon()

                except RequestError as err:
                    msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to turn on {device.name}: {str(err)}"}))
                     
            elif cmd == 'turnoff':
                device = api.devices[request['id']]
                try:
                    msg_write(json.dumps({'msg': 'status', 'status': f"Turning lamp {device.name} off"}))
                    await device.turnoff()
                except RequestError as err:
                    msg_write(json.dumps({'msg': 'error', 'error': f"Error when trying to turn off {device.name}: {str(err)}"}))

    
# actual start of the program
    
asyncio.run(main(sys.argv))
