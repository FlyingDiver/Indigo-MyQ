"""Python3 Wrapper for MyQ"""
import asyncio
import logging
import sys

from aiohttp import ClientSession

from pymyq import login
from pymyq.errors import MyQError, RequestError
from pymyq.garagedoor import STATE_OPEN, STATE_CLOSED

async def main(args: vector) -> None:

    logging.basicConfig(level=logging.DEBUG)
    async with ClientSession() as websession:
        try:
            # Create an API object:
            api = await login(args[0], args[1], websession)


        except MyQError as err:
            _LOGGER.error("There was an error: {}".format(err))


_LOGGER = logging.getLogger()

asyncio.run(main(sys.argv))
