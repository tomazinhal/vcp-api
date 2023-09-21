#!/usr/bin/env python

import asyncio

import structlog
from websockets.server import serve

L = structlog.get_logger(__name__)


async def echo(websocket):
    async for message in websocket:
        L.debug(f"received '{message}'")
        L.debug(f"sending  '{message}'")
        await websocket.send(message)


async def main():
    async with serve(echo, "localhost", 8765):
        L.debug("Running WS backend on localhost:8765")
        await asyncio.Future()  # run forever


asyncio.run(main())
