import asyncio
from typing import List, Optional, Union

import models
import websockets
from exceptions import NoHandlerImplementedError, NoModelImplementedError
from handler import ChargerHandler
from ocpp.exceptions import OCPPError
from ocpp.messages import (
    Call,
    CallError,
    CallResult,
    MessageType,
    unpack,
    validate_payload,
)
from ocpp.v16.enums import Action
from structlog import get_logger
from websockets.client import WebSocketClientProtocol

logger = get_logger(__name__)


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
            await self.incoming_message_handler()
        else:
            logger.debug("abstraction or connection is not ready")

    def log_payload(self, call: Call):
        self.exchange_buffer.append(call)

    async def is_up(self):
        try:
            await self.connection.ping()
            return True
        except Exception as e:
            logger.debug(e)
        return False

    def prepare_payload_for_call(self, action: Action, **kwargs):
        """Prepare a Call originating from the CS."""
        data = {}
        try:
            data = self.abstraction.create_data_for_payload(action, **kwargs)
        except NoModelImplementedError:
            logger.warning("Action %s is not implemented", action)
        try:
            return self.handler.create_payload(action, **data)
        except NoHandlerImplementedError:
            logger.warning("Can not create Call for %s", action)
        raise NotImplementedError

    async def send_controlled_call(self, action: Action, payload):
        call_gen = self.handler.call_generator(payload)
        try:
            call = await call_gen.__anext__()
            self.abstraction.handle_created_call(call)
            self.log_payload(call)
            self.abstraction.call_message_id_to_action_map[call.unique_id] = call.action
            response = await call_gen.__anext__()
            self.abstraction.handle_validated_call_response(response)
            logger.info("FINISHED SEND CONTROLLED CALL")
        except StopAsyncIteration:
            logger.warning("Nothing to step into on the async generator")
        except TimeoutError:
            logger.warning("No response in time for action %s", action)

    async def send_message_to_backend(self, action: Action, **kwargs):
        logger.debug("Action: %s with Kwargs: %s", action, kwargs)
        try:
            payload = self.prepare_payload_for_call(action, **kwargs)
        except NotImplementedError:
            logger.warning("Can't send Call for %s", action)
            return
        await self.send_controlled_call(action, payload)

    async def incoming_message_handler(self):
        """Listener Calls from the CSMS."""
        while True:
            response = None
            message = await self.connection.recv()
            logger.info("%s: received message %s", self.abstraction.id, message)
            msg: Union[Call, CallError, CallResult] = unpack(message)
            try:
                validate_payload(msg, ocpp_version=self.handler._ocpp_version)
            except OCPPError as error:
                response = msg.create_call_error(error).to_json()
                await self.handler._send(response)
                return
            self.log_payload(msg)
            match msg.message_type_id:
                case MessageType.Call:
                    self.abstraction.receive_csms_call(msg)
                    response = await self.handler.handle_csms_call(msg)
                    asyncio.create_task(self.follow_incoming_messages(msg, response))
                case MessageType.CallResult | MessageType.CallError:
                    self.handler.put_in_response_queue(msg)

    async def follow_incoming_messages(
        self,
        message: Union[Call],
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
        if not hasattr(message, "action"):
            logger.warning(f"Can not get action from {message.payload}")
            return
        data = self.abstraction.after_cs_response(request=message, response=response)
        msg = await self.handler.after_cs_response(
            request=message, response=response, **data
        )
        if msg is None:
            return
        send_generator = self.handler.call_generator(payload=msg)
        async for _ in send_generator:
            pass

    async def create_ws_connection(self, backend_url):
        backend_url = "/".join([backend_url, self.abstraction.id])
        logger.debug("Connecting to %s", backend_url)
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
                logger.debug("Connection rejected, can't close unopened connection.")
            raise ConnectionRefusedError
