import asyncio

import pytest


async def loop():
    i = 0
    while True:
        i += 1
        await asyncio.sleep(1)
        yield i


@pytest.mark.asyncio
async def test_loop():
    async for i in loop():
        print(i)
