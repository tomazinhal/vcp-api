import asyncio
from dataclasses import asdict
from typing import Callable, Dict, Union

import structlog
from exceptions import NoHandlerImplementedError
from features.core import CoreFeature
from features.remote_trigger import RemoteTriggerFeature
from features.smart_charging import SmartChargingFeature
from ocpp.charge_point import camel_to_snake_case, remove_nones, snake_to_camel_case
from ocpp.exceptions import OCPPError
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
            self, HandlerType.CALL_FACTORY
        )

    def create_payload(self, action, **kwargs):
        try:
            return self.action_payload_map[action](**kwargs)
        except KeyError:
            raise NoHandlerImplementedError(
                "Nothing to do from models side for %s", action
            )

    async def call(self, payload, suppress=True, unique_id=None):
        call: Call = self.create_call(payload, unique_id)
        response = await self.half_duplex_request(call)
        validated_payload = self.handle_call_response(payload, call, response, suppress)
        return validated_payload

    async def call_generator(self, payload, suppress=True, unique_id=None):
        call: Call = self.create_call(payload, unique_id)
        yield call
        response = await self.half_duplex_request(call)
        yield response
        validated_response = self.handle_call_response(
            payload, call, response, suppress
        )
        yield validated_response

    def create_call(self, payload, unique_id=None):
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

    async def half_duplex_request(self, call):
        # Use a lock to prevent make sure that only 1 message can be send at a
        # a time.
        async with self._call_lock:
            message = call.to_json()
            L.debug("%s: sending %s", self.id, message)
            await self._send(message)
            try:
                response = await self._get_specific_response(
                    call.unique_id, self._response_timeout
                )
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError(
                    f"Waited {self._response_timeout}s for response on "
                    f"{call.to_json()}."
                )
        return response

    def handle_call_response(self, payload, call, response, suppress=False):
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
