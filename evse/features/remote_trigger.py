"""
TriggerMessage
"""
from typing import Optional

from ocpp.routing import after, on
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, MessageTrigger
from structlog import get_logger

L = get_logger(__name__)


class RemoteTriggerFeature:
    @on(Action.TriggerMessage)
    def on_trigger_message(
        self, requested_message: MessageTrigger, connector_id: Optional[int] = None
    ):
        if self.supports_remote_trigger:
            return call_result.TriggerMessagePayload(
                status=call_result.TriggerMessageStatus.accepted
            )
        return call_result.TriggerMessagePayload(
            status=call_result.TriggerMessageStatus.not_implemented
        )

    @after(Action.TriggerMessage)
    def after_trigger_message(
        self, requested_message: MessageTrigger, connector_id: Optional[int] = None
    ):
        abstraction_input = yield (requested_message, connector_id)
        if not self.supports_remote_trigger:
            return
        match requested_message:
            case MessageTrigger.boot_notification:
                return self.boot_notification_payload(abstraction_input)
            case MessageTrigger.status_notification:
                return self.status_notification_payload(abstraction_input)
            case _:
                """
                - MessageTrigger.heartbeat
                - MessageTrigger.meter_values
                - MessageTrigger.firmware_status_notification
                """
                raise NotImplementedError("Nothing to do for %s", requested_message)
