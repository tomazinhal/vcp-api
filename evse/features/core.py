"""
ChangeConfig
GetConfig
RemoteStart
RemoteStop
Reset
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from ocpp.routing import after, on
from ocpp.v16 import call, call_result
from ocpp.v16.enums import Action, ChargePointErrorCode, ChargePointStatus, ResetType
from structlog import get_logger
from utils import HandlerType, handler

L = get_logger(__name__)


class CoreFeature:
    @handler(Action.BootNotification, HandlerType.CALL_FACTORY)
    def boot_notification_payload(self, **data):
        model = data.get("model", "unknown")
        vendor = data.get("vendor", "unknown")
        # get other optional attributes like firmware...
        firmware = data.get("firmware", None)
        return call.BootNotificationPayload(
            charge_point_model=model,
            charge_point_vendor=vendor,
            firmware_version=firmware,
        )

    @handler(Action.StatusNotification, HandlerType.CALL_FACTORY)
    def payload_for_status_notification(self, **kwargs):
        connector = kwargs.get("connector_id", 0)
        status = kwargs.get("status", ChargePointStatus.available)
        error_code = kwargs.get("error", ChargePointErrorCode.no_error)
        info = kwargs.get("info", None)
        return call.StatusNotificationPayload(
            connector_id=connector, status=status, error_code=error_code, info=info
        )

    @handler(Action.StartTransaction, HandlerType.CALL_FACTORY)
    def payload_for_start_transaction(self, **kwargs):
        start = kwargs.get("meter_start", 0)
        rfid = kwargs.get("rfid", "superrfid")
        connector_id = kwargs.get("connector_id", 1)
        return call.StartTransactionPayload(
            connector_id=connector_id,
            id_tag=rfid,
            meter_start=start,
            timestamp=str(datetime.now()),
        )

    @handler(Action.StartTransaction, HandlerType.CALL_RESULT_PAYLOAD)
    def handle_start_transaction_response(self, payload):
        # check whether StartTransaction was accepted or not and retrieve
        # transaction id
        pass

    @on(Action.ChangeConfiguration)
    def on_change_configuration(key: str, value: Any):
        return call_result.ChangeConfigurationPayload()

    @on(Action.GetConfiguration)
    def on_get_configuration(key: Optional[List] = None):
        return call_result.GetConfigurationPayload()

    @on(Action.RemoteStartTransaction)
    def on_remote_start_transaction(
        id_tag: str,
        connector_id: Optional[int] = None,
        charging_profile: Optional[Dict] = None,
    ):
        return call_result.RemoteStartTransactionPayload()

    @after(Action.RemoteStartTransaction)
    def on_remote_start_transaction():
        pass

    @on(Action.RemoteStopTransaction)
    def on_remote_stop_transaction(transaction_id: str):
        return call_result.RemoteStopTransactionPayload()

    @after(Action.RemoteStopTransaction)
    def on_remote_stop_transaction():
        pass

    @on(Action.Reset)
    def on_reset(type: ResetType):
        return call_result.ResetPayload()

    @after(Action.Reset)
    def after_reset():
        pass
