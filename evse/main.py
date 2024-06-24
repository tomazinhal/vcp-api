import asyncio
from copy import copy
from typing import Optional

import controller
from fastapi import FastAPI, HTTPException, status
from ocpp.v16.enums import Action, ChargePointErrorCode, ChargePointStatus
from structlog import get_logger

L = get_logger(__name__)

BACKENDURL = "ws://localhost:8765"
evse = FastAPI()
charger = controller.EVSE()


@evse.get("/whoami")
async def whoami():
    abstraction = copy(charger.abstraction)
    connected = await charger.is_up()
    L.info("Charger %s is %s", abstraction.id, "up" if connected else "not up")
    return abstraction


@evse.put("/setup")
def setup(charger_id: str, number_connectors: int, password: str):
    charger.create(charger_id, number_connectors, password)
    return charger.abstraction


@evse.get("/is_up")
async def connection_is_up():
    if await charger.is_up():
        return True
    else:
        return False


@evse.get("/history")
async def get_history():
    return charger.exchange_buffer


@evse.post("/connect", status_code=status.HTTP_200_OK)
async def connect(backend_url: str = BACKENDURL):
    try:
        charger.connection = await charger.create_ws_connection(backend_url)
    except ConnectionRefusedError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    asyncio.create_task(charger.run())


@evse.post("/bootnotification")
async def boot_notification(model: str, vendor: str):
    return await charger.send_message_to_backend(
        Action.BootNotification, charge_point_model=model, charge_point_vendor=vendor
    )


@evse.post("/authorize")
async def authorize(rfid: str):
    return await charger.send_message_to_backend(Action.Authorize, rfid=rfid)


@evse.post("/data_transfer")
async def data_transfer():
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@evse.post("/diagnostics_status_notification")
async def diagnostics_status_notification():
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@evse.post("/firmware_status_notification")
async def firmware_status_notification():
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@evse.post("/heartbeat")
async def heartbeat():
    return await charger.send_message_to_backend(
        Action.Heartbeat,
    )


@evse.post("/meter_values")
async def meter_values(connector_id: int = 1, voltage: int = 230, current: int = 0):
    return await charger.send_message_to_backend(
        Action.MeterValues, connector_id, connector_id, voltage=voltage, current=current
    )


@evse.post("/start_transaction")
async def start_transaction(rfid: str, connector_id: int = 1, meter_start: int = 0):
    # timestamp is required to send a start transaction
    return await charger.send_message_to_backend(
        Action.StartTransaction,
    )


@evse.post("/status_notification")
async def status_notification(
    status: ChargePointStatus,
    connector_id: int = 0,
    error: Optional[ChargePointErrorCode] = None,
):
    return await charger.send_message_to_backend(
        Action.StatusNotification,
    )


@evse.post("/stop_transaction")
async def stop_transaction():
    return await charger.send_message_to_backend(
        Action.StopTransaction,
    )


@evse.get("/")
async def root():
    return {"message": "Hello World"}
