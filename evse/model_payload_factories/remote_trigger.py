"""
TriggerMessage
"""
from typing import Optional, Union

from ocpp.charge_point import camel_to_snake_case
from ocpp.messages import Call, CallError, CallResult
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, MessageTrigger
from structlog import get_logger
from utils import HandlerType, handler

logger = get_logger(__name__)


class RemoteTriggerFeature:
    supports_remote_trigger: bool = True

    @handler(Action.TriggerMessage, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def on_trigger_message(
        self, requested_message: MessageTrigger, connector_id: Optional[int] = None
    ):
        logger.debug(f"Abstraction handles remote trigger here for {requested_message}")
        if not self.supports_remote_trigger:
            logger.info("does not support after trigger message")

    @handler(Action.TriggerMessage, HandlerType.AFTER_CALL_RESPONSE_FROM_CP)
    def after_trigger_message(
        self, request: Call, response: Union[CallResult, CallError], **kwargs
    ):
        trigger_message = call.TriggerMessagePayload(
            **camel_to_snake_case(request.payload)
        )
        if not self.supports_remote_trigger:
            logger.info("No support for TriggerMessage.")
            return
        match trigger_message.requested_message:
            case MessageTrigger.boot_notification:
                return self.payload_for_boot_notification(**kwargs)
            case MessageTrigger.status_notification:
                return self.payload_for_status_notification(**kwargs)
            case _:
                """
                - MessageTrigger.heartbeat
                - MessageTrigger.meter_values
                - MessageTrigger.firmware_status_notification
                """
                raise NotImplementedError(
                    "Nothing to do for %s", request.requested_message
                )
