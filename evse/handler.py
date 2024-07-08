import asyncio
import inspect
from dataclasses import asdict
from typing import Callable, Dict, Union

import structlog
from exceptions import NoHandlerImplementedError
from features.core import CoreFeature
from features.remote_trigger import RemoteTriggerFeature
from features.smart_charging import SmartChargingFeature
from ocpp.charge_point import camel_to_snake_case, remove_nones, snake_to_camel_case
from ocpp.exceptions import NotSupportedError, OCPPError
from ocpp.messages import Call, CallError, CallResult, MessageType, validate_payload
from ocpp.v16 import ChargePoint
from ocpp.v16.enums import Action
from utils import HandlerType, create_route_map

logger = structlog.get_logger(__name__)


class ChargerHandler(
    ChargePoint, CoreFeature, SmartChargingFeature, RemoteTriggerFeature
):
    def __init__(self, charger_id, connection, response_timeout=30):
        super().__init__(
            id=charger_id, connection=connection, response_timeout=response_timeout
        )
        self.action_payload_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.BEFORE_CALL_REQUEST_FROM_CP
        )
        self.on_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.ON_CALL_REQUEST_FROM_CSMS
        )
        self.after_response_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.ON_CALL_RESPONSE_FROM_CSMS
        )

        self.follow_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.AFTER_CALL_RESPONSE_FROM_CP
        )

    def create_payload(self, action, **kwargs):
        try:
            logger.info(f"making payload for {action}")
            return self.action_payload_map[action](**kwargs)
        except KeyError:
            raise NoHandlerImplementedError(
                "Nothing to do from models side for %s", action
            )

    async def call_generator(self, payload, suppress=True, unique_id=None):
        """
        Generator that yields control:
        1. after Call for request is created
        3. after response for a Call is validated
        """
        call: Call = self.create_call(payload, unique_id)
        yield call
        response = await self.send_call(call)
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
            logger.debug("%s: sending %s", self.id, message)
            await self._send(message)
            if isinstance(call, CallError) or isinstance(call, CallResult):
                logger.debug("Message is CallError | CallResult - not expecting reply")
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
            logger.warning("Received a CALLError: %s'", response)
            if suppress:
                return
            raise response.to_exception()
        else:
            response.action = call.action
            validate_payload(response, self._ocpp_version)

        snake_case_payload = camel_to_snake_case(response.payload)
        cls = getattr(self._call_result, payload.__class__.__name__)  # noqa
        return cls(**snake_case_payload)

    def put_in_response_queue(self, message):
        self._response_queue.put_nowait(message)

    async def on_message_handler(self, msg: Call) -> Union[CallResult, CallError]:
        """
        Handles a message by using the handler function in `on_request_map`
        and returns a Call | CallError.
        """
        validate_payload(msg, self._ocpp_version)
        snake_case_payload = camel_to_snake_case(msg.payload)
        try:
            handler = self.on_request_map[msg.action]
        except KeyError:
            raise NotSupportedError(
                description="NotImplemented",
                details={"cause": f"No 'on' handler for {msg.action} registered."},
            )

        try:
            response = handler(**snake_case_payload)
            if inspect.isawaitable(response):
                response = await response
            return response
        except Exception as e:
            logger.exception("Error while handling request '%s'", msg)
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
        self.handle_csms_call(msg=msg)

    async def handle_csms_call(self, msg: Call) -> Union[CallResult, CallError]:
        """
        Receives a Call and call the respective handler functions.

        1. on_message_handler
        2. prepare_response
        3. send_call
        4. follow_request function
        """
        try:
            handled_output = await self.on_message_handler(msg)
        except (OCPPError, NotSupportedError) as error:
            logger.exception("Error while handling request '%s'", msg)
            response = msg.create_call_error(error).to_json()
            await self._send(response)
            return
        response = self.prepare_response(msg, handled_output)
        logger.debug("%s sending: %s", self.id, response)
        await self.send_call(response)
        return response

    async def after_cs_response(
        self, request: Call, response: Union[CallResult, CallError], **kwargs
    ):
        try:
            handler = self.follow_request_map[request.action]
            return handler(request, response, **kwargs)
        except KeyError:
            logger.debug(f"There is nothing to do after handling {request.action}")
