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

logger = get_logger(__name__)


class CoreFeature:
    # --------------- SENDING CALLS FROM THE CHARGE POINT
    @handler(Action.BootNotification, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
    def boot_notification_payload(self, **data):
        model = data.get("charge_point_model", "unknown")
        vendor = data.get("charge_point_vendor", "unknown")
        # get other optional attributes like firmware...
        firmware = data.get("firmware", None)
        logger.debug("feature handler for bootnitifacion")
        return call.BootNotificationPayload(
            charge_point_model=model,
            charge_point_vendor=vendor,
            firmware_version=firmware,
        )

    @handler(Action.StatusNotification, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
    def payload_for_status_notification(self, **kwargs):
        connector = kwargs.get("connector_id", 0)
        status = kwargs.get("status", ChargePointStatus.available)
        error_code = kwargs.get("error", ChargePointErrorCode.no_error)
        info = kwargs.get("info", None)
        return call.StatusNotificationPayload(
            connector_id=connector, status=status, error_code=error_code, info=info
        )

    @handler(Action.StartTransaction, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
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

    @handler(Action.Heartbeat, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
    def on_heartbeat(self, **kwargs):
        return call.HeartbeatPayload()

    @handler(Action.Authorize, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
    def on_authorize(self, **kwargs):
        return call.AuthorizePayload(id_tag=kwargs.get("id_tag", ""))

    # --------------- RECEIVING CALLS FROM THE CENTRAL SYSTEM
    @handler(Action.BootNotification, HandlerType.ON_CALL_RESPONSE_FROM_CSMS)
    def handle_boot_notification_response(self, **kwargs):
        # do something with the time sync provided by csms
        logger.warning("After receiving BootNotification.CallResult")

    @handler(Action.ChangeConfiguration, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def on_change_configuration(self, key: str, value: Any):
        return call_result.ChangeConfigurationPayload(
            status=call_result.ConfigurationStatus.accepted
        )

    @handler(Action.GetConfiguration, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def on_get_configuration(self, **kwargs):
        logger.info(f"On get config with {kwargs}")
        config = {
            "HeartbeatInterval": 100,
            "MeterValuesSampledData": 10,
            "MeterValueSampleInterval": ["Power.Active.Import"],
            "NumberOfConnectors": 1,
            "AuthorizeRemoteTxRequests": "false",
        }
        return call_result.GetConfigurationPayload(
            configuration_key=[
                {"key": k, "readonly": False, "value": str(v)}
                for k, v in config.items()
            ]
        )

    @handler(Action.RemoteStartTransaction, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def on_remote_start_transaction(
        id_tag: str,
        connector_id: Optional[int] = None,
        charging_profile: Optional[Dict] = None,
    ):
        return call_result.RemoteStartTransactionPayload()

    @handler(Action.RemoteStopTransaction, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def on_remote_stop_transaction(transaction_id: str):
        return call_result.RemoteStopTransactionPayload()

    @handler(Action.Reset, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def on_reset(type: ResetType):
        return call_result.ResetPayload()

    # --------------- ACTIONS AFTER REPLYING TO CENTRAL SYSTEM
    @handler(Action.StartTransaction, HandlerType.AFTER_CALL_RESPONSE_FROM_CP)
    def handle_start_transaction_response(self, payload):
        pass

    @handler(Action.RemoteStartTransaction, HandlerType.AFTER_CALL_RESPONSE_FROM_CP)
    def on_remote_start_transaction():
        pass

    @handler(Action.RemoteStopTransaction, HandlerType.AFTER_CALL_RESPONSE_FROM_CP)
    def on_remote_stop_transaction():
        pass

    @handler(Action.Reset, HandlerType.AFTER_CALL_RESPONSE_FROM_CP)
    def after_reset():
        pass
