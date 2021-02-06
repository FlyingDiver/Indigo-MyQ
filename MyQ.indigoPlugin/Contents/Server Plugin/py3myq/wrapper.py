"""Python3 Wrapper for MyQ"""
import asyncio
import logging
import sys
import json

from aiohttp import ClientSession

from pymyq import login
from pymyq.errors import MyQError, RequestError

async def main(args) -> None:

    logging.basicConfig(level=logging.INFO)
    async with ClientSession() as websession:
        try:
            api = await login(sys.argv[1], sys.argv[2], websession)

        except MyQError as err:
            _LOGGER.error("There was an error: {}".format(err))

        else:
            _LOGGER.info("Login complete")
            
            for account in api.accounts:
                
                data = {'data': 'account', 'id': account, 'name': api.accounts[account]}
                sys.stdout.write(json.dumps(data))
                sys.stdout.write('\n')

                if len(api.covers) != 0:
                    for device_id in api.covers:
                        if api.devices[device_id].account == account:
                            device = api.devices[device_id]
                            data = {
                                'data': 'device', 
                                'id': device_id, 
                                'name': device.name, 
                                'state': device.state, 
                                'online': device.online, 
                                'device_family': device.device_family, 
                                'device_platform': device.device_platform,
                                'device_type': device.device_type,
                                'firmware_version': device.firmware_version,
                            }
                            sys.stdout.write(json.dumps(data))
                            sys.stdout.write('\n')



_LOGGER = logging.getLogger()
asyncio.run(main(sys.argv))
