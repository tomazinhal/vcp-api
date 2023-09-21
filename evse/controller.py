from typing import List, Optional, Union

import models
import websockets
from exceptions import NoHandlerImplementedError, NoModelImplementedError
from handler import ChargerHandler
from ocpp.messages import Call, CallError, CallResult
from ocpp.v16.enums import Action
from structlog import get_logger
from websockets.client import WebSocketClientProtocol

L = get_logger(__name__)


class EVSE:
    handler: Optional[ChargerHandler] = None
    abstraction: Optional[models.Charger] = None
    connection: Optional[WebSocketClientProtocol] = None
    exchange_buffer: List = []

    def __init__(self):
        self.abstraction = models.Charger.simple()
        self.handler = None
        self.connection = None

    def create(self, charger_id: str, number_connectors: int):
        self.abstraction = models.Charger.create(charger_id, number_connectors)

    async def run(self):
        if self.abstraction.ready and await self.is_up():
            self.handler = ChargerHandler(
                self.abstraction.id, connection=self.connection, response_timeout=1
            )
            await self.message_handler()
        else:
            L.debug("abstraction or connection is not ready")

    async def start(self):
        try:
            while True:
                if self.connection:
                    L.debug()
                    await self.connection.recv()
        except:
            L.error("E", exc_info=1)
            self.connection.close()

    def log_payload(self, call):
        self.exchange_buffer.append(call)

    def prepare_payload_for_call(self, action: Action, **kwargs):
        data = {}
        try:
            data = self.abstraction.create_data_for_payload(action, **kwargs)
        except NoModelImplementedError:
            L.warning("Action %s is not implemented", action)
        try:
            return self.handler.create_payload(action, **data)
        except NoHandlerImplementedError:
            L.warning("Can not create Call for %s", action)
        raise NotImplementedError

    async def send_message_to_backend(self, action: Action, **kwargs):
        L.debug("Action: %s", action)
        L.debug("Kwargs %s", kwargs)
        try:
            payload = self.prepare_payload_for_call(action, **kwargs)
        except NotImplementedError:
            L.warning("Can't send Call for %s", action)
            return
        call_gen = self.handler.call_generator(payload)
        try:
            call = await call_gen.__anext__()
            self.abstraction.handle_created_call(call)
            self.log_payload(call)
            response = await call_gen.__anext__()
            self.abstraction.handle_call_response(response)
            validated_response = await call_gen.__anext__()
            self.abstraction.handle_validated_call_response(validated_response)
        except StopAsyncIteration:
            L.warning("Nothing to step into on the async generator")
        except TimeoutError:
            L.warning("No response in time for action %s", action)

    async def is_up(self):
        try:
            await self.connection.ping()
            return True
        except Exception as e:
            L.debug(e)
        return False

    async def message_handler(self):
        while True:
            message = await self.connection.recv()
            message_handled: bool = False
            L.info("%s: received message %s", self.abstraction.id, message)
            try:
                route_message_generator = self.handler.route_message(message)
                # validate info with abstraction
                msg: Union[
                    Call, CallError, CallResult
                ] = await route_message_generator.__anext__()
                self.abstraction.handle(msg)
                await route_message_generator.__anext__()
                message_handled = True
            except StopAsyncIteration:
                L.info("handling received message finished")
            try:
                # handle after action
                # i.e. after TriggerMessage being accepted we need to
                # act on the requested message.
                if not message_handled:
                    L.info("Message %s not handled so nothing to after.", message)
                    return
            except Exception:
                L.info("after handling received message finished")

    async def create_ws_connection(self, backend_url):
        backend_url = "/".join([backend_url, self.abstraction.id])
        L.debug("Connecting to %s", backend_url)
        try:
            connection = await websockets.client.connect(
                backend_url, subprotocols=["ocpp1.6"]
            )
            return connection
        except:
            connection.close()
            raise ConnectionRefusedError
