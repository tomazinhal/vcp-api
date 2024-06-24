import asyncio
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

    def create(
        self, charger_id: str, number_connectors: int, password: str | None = None
    ):
        self.abstraction = models.Charger.create(
            charger_id, number_connectors, password
        )

    async def run(self):
        if self.abstraction.ready and await self.is_up():
            self.handler = ChargerHandler(
                self.abstraction.id, connection=self.connection, response_timeout=1
            )
            await self.handle_incoming_messages()
        else:
            L.debug("abstraction or connection is not ready")

    def log_payload(self, call: Call):
        self.exchange_buffer.append(call)

    async def is_up(self):
        try:
            await self.connection.ping()
            return True
        except Exception as e:
            L.debug(e)
        return False

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

    async def send_controlled_call(self, action: Action, payload):
        call_gen = self.handler.call_generator(payload)
        try:
            call = await call_gen.__anext__()
            self.abstraction.handle_created_call(call)
            self.log_payload(call)
            self.abstraction.call_message_id_to_action_map[call.unique_id] = call.action
            response = await call_gen.__anext__()
            self.abstraction.handle_call_response(response)
            validated_response = await call_gen.__anext__()
            self.abstraction.handle_validated_call_response(validated_response)
            L.info("FINISHED SEND CONTROLLED CALL")
        except StopAsyncIteration:
            L.warning("Nothing to step into on the async generator")
        except TimeoutError:
            L.warning("No response in time for action %s", action)

    async def send_message_to_backend(self, action: Action, **kwargs):
        L.debug("Action: %s with Kwargs: %s", action, kwargs)
        try:
            payload = self.prepare_payload_for_call(action, **kwargs)
        except NotImplementedError:
            L.warning("Can't send Call for %s", action)
            return
        await self.send_controlled_call(action, payload)

    async def handle_incoming_messages(self):
        while True:
            message_handled: bool = False
            response = None
            message = await self.connection.recv()
            L.info("%s: received message %s", self.abstraction.id, message)
            route_message_generator = self.handler.route_message(message)
            try:
                msg: Union[
                    Call, CallError, CallResult
                ] = await route_message_generator.__anext__()
                self.log_payload(msg)
                response = await route_message_generator.__anext__()
                message_handled = True
            except StopAsyncIteration:
                message_handled = True
            except Exception as e:
                L.critical("Fatal error while handling message", exc_info=e)
                if not message_handled:
                    L.info("Message %s not handled so nothing to after.", message)
                    return
            asyncio.create_task(self.follow_incoming_messages(msg, response))

    async def follow_incoming_messages(
        self,
        msg: Union[Call, CallError, CallResult],
        response: Union[CallError, CallResult, None],
    ):
        """
        After a messages has been sent or a Call has been replied to,
        some action may be required to complete the expected flow.

        i.e:
            If a CSMS sends a TriggerMessage.BootNotification, the
            CP should reply whether it accepts this TriggerMessage or not.
            If it accepts the TriggerMessage, then a BootNotification should
            be sent as soon as possible.
        """
        if not hasattr(msg, "action"):
            return
        payload = self.abstraction.follow_up_handle(msg, response)
        msg = await self.handler._follow_request_call(msg.action, payload)
        if msg is None:
            return
        await self.send_controlled_call(msg.action, payload)
        # may do nothing since it's not required

    async def create_ws_connection(self, backend_url):
        backend_url = "/".join([backend_url, self.abstraction.id])
        L.debug("Connecting to %s", backend_url)
        try:
            connection = await websockets.client.connect(
                backend_url,
                subprotocols=["ocpp1.6"],
                ssl=None,
                extra_headers={
                    "Authorization": websockets.headers.build_authorization_basic(
                        self.abstraction.id, self.abstraction.password
                    )
                },
            )
            return connection
        except:
            try:
                connection.close()
            except UnboundLocalError:
                L.debug("Connection rejected, can't close unopened connection.")
            raise ConnectionRefusedError
