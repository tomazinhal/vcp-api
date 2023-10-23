import asyncio
import inspect
from dataclasses import asdict
from typing import Callable, Dict, Union

import structlog
from ocpp.charge_point import camel_to_snake_case, remove_nones, snake_to_camel_case
from ocpp.exceptions import NotSupportedError, OCPPError
from ocpp.messages import (
    Call,
    CallError,
    CallResult,
    MessageType,
    unpack,
    validate_payload,
)
from ocpp.v16 import ChargePoint
from ocpp.v16.enums import Action

from exceptions import NoHandlerImplementedError
from features.core import CoreFeature
from features.remote_trigger import RemoteTriggerFeature
from features.smart_charging import SmartChargingFeature
from utils import HandlerType, create_route_map

L = structlog.get_logger(__name__)


class ChargerHandler(
    ChargePoint, CoreFeature, SmartChargingFeature, RemoteTriggerFeature
):
    def __init__(self, charger_id, connection, response_timeout=30):
        super().__init__(
            charger_id, connection=connection, response_timeout=response_timeout
        )
        self.action_payload_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.BEFORE_REQUEST
        )
        self.on_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.ON_REQUEST
        )
        self.after_response_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.AFTER_RESPONSE
        )

        self.follow_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.FOLLOW_REQUEST
        )

    def create_payload(self, action, **kwargs):
        try:
            L.info(f"making payload for {action}")
            return self.action_payload_map[action](**kwargs)
        except KeyError:
            raise NoHandlerImplementedError(
                "Nothing to do from models side for %s", action
            )

    async def __call(self, payload, suppress=True, unique_id=None):
        call: Call = self.create_call(payload, unique_id)
        response = await self.send_call(call)
        validated_payload = self.handle_response(payload, call, response, suppress)
        return validated_payload

    async def call_generator(self, payload, suppress=True, unique_id=None):
        """
        Generator that yields control:
        1. after Call for request is created
        2. after response for a Call is received
        3. after response for a Call is validated
        """
        call: Call = self.create_call(payload, unique_id)
        yield call
        response = await self.send_call(call)
        yield response
        validated_response = self.handle_response(payload, call, response, suppress)
        yield validated_response

    def create_call(self, payload, unique_id=None) -> Call:
        """
        Create a Call for a given payload
        """
        camel_case_payload = snake_to_camel_case(asdict(payload))
        unique_id = (
            unique_id if unique_id is not None else str(self._unique_id_generator())
        )
        call = Call(
            unique_id=unique_id,
            action=payload.__class__.__name__[:-7],
            payload=remove_nones(camel_case_payload),
        )
        validate_payload(call, self._ocpp_version)
        return call

    async def send_call(self, call: Union[Call, CallResult, CallError]):
        """
        Send a Call request and wait a response through a channel that only
        allows one call to go through at a time.
        """
        # Use a lock to prevent make sure that only 1 message can be send at a
        # a time.
        async with self._call_lock:
            message = call.to_json()
            L.debug("%s: sending %s", self.id, message)
            await self._send(message)
            if isinstance(call, CallError) or isinstance(call, CallResult):
                L.debug("Message is CallError | CallResult - not expecting reply")
                return
            try:
                response = await self._get_specific_response(
                    call.unique_id, self._response_timeout
                )
                return response
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError(
                    f"Waited {self._response_timeout}s for response on "
                    f"{call.to_json()}."
                )

    def handle_response(
        self, payload, call: Call, response, suppress=False
    ) -> Union[CallError, CallResult, None]:
        """
        Handles a response payload and creates a CallResult or CallError from it.

        """
        if response.message_type_id == MessageType.CallError:
            L.warning("Received a CALLError: %s'", response)
            if suppress:
                return
            raise response.to_exception()
        else:
            response.action = call.action
            validate_payload(response, self._ocpp_version)

        snake_case_payload = camel_to_snake_case(response.payload)
        cls = getattr(self._call_result, payload.__class__.__name__)  # noqa
        return cls(**snake_case_payload)

    async def route_message(self, raw_msg):
        """
        Parses any messages received and forwards it to the right route for
        handling the specific message.
        """
        try:
            msg: Union[Call, CallError, CallResult] = unpack(raw_msg)
        except OCPPError as e:
            L.exception(
                "Unable to parse message: '%s', it doesn't seem "
                "to be valid OCPP: %s",
                raw_msg,
                e,
            )
            return
        yield msg
        if msg.message_type_id == MessageType.Call:
            try:
                await self._handle_call(msg)
                L.info("HANDLED %s", msg)
            except OCPPError as error:
                L.exception("Error while handling request '%s'", msg)
                response = msg.create_call_error(error).to_json()
                await self._send(response)
        elif msg.message_type_id in [MessageType.CallResult, MessageType.CallError]:
            self._response_queue.put_nowait(msg)
            return

    async def on_message_handler(self, msg: Call) -> Union[CallResult, CallError]:
        """
        Handles a message by using the handler function in `on_request_map`
        and returns a Call | CallError.
        """
        snake_case_payload = camel_to_snake_case(msg.payload)
        try:
            handler = self.on_request_map[msg.action]
        except KeyError:
            raise NotSupportedError(
                details={"cause": f"No 'on' handler for {msg.action} registered."}
            )

        try:
            response = handler(**snake_case_payload)
            if inspect.isawaitable(response):
                response = await response
            return response
        except Exception as e:
            L.exception("Error while handling request '%s'", msg)
            response = msg.create_call_error(e)
            return response

    def prepare_response(
        self, msg: Call, response: Union[CallResult, CallError]
    ) -> CallResult:
        temp_response_payload = asdict(response)
        response_payload = remove_nones(temp_response_payload)
        camel_case_payload = snake_to_camel_case(response_payload)
        return msg.create_call_result(camel_case_payload)

    async def send_response(self, response):
        validate_payload(response, self._ocpp_version)
        await self._send(response.to_json())

    async def _handle_call(self, msg: Call):
        """
        Receives a Call and call the respective handler functions.

        1. on_message_handler
        2. prepare_response
        3. send_call
        4. follow_request function
        """
        validate_payload(msg, self._ocpp_version)
        snake_case_payload = camel_to_snake_case(msg.payload)

        handled_output = await self.on_message_handler(
            msg
        )  # on_request_map[msg.action]
        response = self.prepare_response(msg, handled_output)
        L.debug("call: %s", response)
        await self.send_call(response)

    async def _follow_request_call(self, action: Action, payload):
        try:
            handler = self.follow_request_map[action]
            # Create task to avoid blocking when making a call inside the
            # after handler
            response = handler(**payload)
            if inspect.isawaitable(response):
                await response
        except KeyError:
            # '_on_after' hooks are not required. Therefore ignore exception
            # when no '_on_after' hook is installed.
            L.debug(f"There is nothing to do after {action}")
