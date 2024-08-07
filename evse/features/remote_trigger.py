"""
TriggerMessage
"""
from typing import Optional, Union

from ocpp.charge_point import camel_to_snake_case
from ocpp.messages import Call, CallError, CallResult
from ocpp.routing import after, on
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
        if not self.supports_remote_trigger:
            return call_result.TriggerMessagePayload(
                status=call_result.TriggerMessageStatus.not_implemented
            )
        return call_result.TriggerMessagePayload(
            status=call_result.TriggerMessageStatus.accepted
        )

    @handler(Action.TriggerMessage, HandlerType.AFTER_CALL_RESPONSE_FROM_CP)
    def after_trigger_message(
        self, request: Call, response: Union[CallResult, CallError], **kwargs
    ):
        trigger_message = call.TriggerMessagePayload(
            **camel_to_snake_case(request.payload)
        )
        if not self.supports_remote_trigger:
            return
        match trigger_message.requested_message:
            case MessageTrigger.boot_notification:
                return self.boot_notification_payload(**kwargs)
            case MessageTrigger.status_notification:
                return self.status_notification_payload(**kwargs)
            case _:
                """
                - MessageTrigger.heartbeat
                - MessageTrigger.meter_values
                - MessageTrigger.firmware_status_notification
                """
                raise NotImplementedError(
                    "Nothing to do for %s", request.requested_message
                )
