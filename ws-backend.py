#!/usr/bin/env python

import asyncio

import structlog
from websockets.server import serve

logger = structlog.get_logger(__name__)


async def echo(websocket):
    logger.debug("receiving")
    await websocket.send(
        '[2,"5c7018a3-aa08-421d-b9c2-5dad3d584ec3","TriggerMessage",{"requestedMessage":"BootNotification"}]'
    )
    async for message in websocket:
        logger.debug(f"received '{message}'")
        # logger.debug(f"sending  '{message}'")
        # await websocket.send(message)


async def main():
    async with serve(echo, "localhost", 8765):
        logger.debug("Running WS backend on localhost:8765")
        await asyncio.Future()  # run forever


asyncio.run(main())
