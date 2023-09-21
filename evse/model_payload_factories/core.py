from ocpp.v16.enums import Action
from structlog import get_logger
from utils import HandlerType, handler

L = get_logger(__name__)


class Core:
    @handler(Action.BootNotification, HandlerType.CALL_FACTORY)
    def payload_for_boot_notification(self, **kwargs):
        kwargs.update({"firmware": "virtual firmware 1.0.0"})
        return kwargs

    @handler(Action.StatusNotification, HandlerType.CALL_FACTORY)
    def payload_for_status_notification(self, **kwargs):
        return kwargs

    @handler(Action.StartTransaction, HandlerType.CALL_RESULT_PAYLOAD)
    def handler_for_start_transaction_response(self, payload):
        pass
