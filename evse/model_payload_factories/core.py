from typing import Dict, List

from ocpp.v16.enums import Action
from structlog import get_logger
from utils import HandlerType, handler

L = get_logger(__name__)

DEFAULT_FIRMWARE = "virtual firmware 1.0.0"
DEFAULT_HEARTBEAT_INTERVAL = 3600
DEFAULT_METER_VALUES_INTERVAL = 30
DEFAULT_METER_VALUES_SAMPLE_INTERVAL = ["Power.Active.Import"]


class Core:
    # configurations
    heartbeat_interval: int
    meter_values_interval: int
    meter_values_sample_data: List
    configuration: Dict

    def __init__(self) -> None:
        self.heartbeat_interval = DEFAULT_HEARTBEAT_INTERVAL
        self.meter_values_interval = DEFAULT_METER_VALUES_INTERVAL
        self.meter_values_sample_data = DEFAULT_METER_VALUES_SAMPLE_INTERVAL
        self.configuration = {}

    @handler(Action.BootNotification, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
    def payload_for_boot_notification(self, **kwargs):
        L.info("model boot notification before request from cp")
        kwargs.update({"firmware": DEFAULT_FIRMWARE})
        return kwargs

    @handler(Action.Heartbeat, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
    def opayload_for__heartbeat(self, **kwargs):
        return {}

    @handler(Action.StatusNotification, HandlerType.BEFORE_CALL_REQUEST_FROM_CP)
    def payload_for_status_notification(self, **kwargs):
        return kwargs

    @handler(Action.StartTransaction, HandlerType.AFTER_CALL_RESPONSE_FROM_CP)
    def handler_for_start_transaction_response(self, payload):
        pass

    @handler(Action.ChangeConfiguration, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def handler_for_change_configuration(self, key: str, value: str):
        self.configuration[key] = value
        return True

    @handler(Action.GetConfiguration, HandlerType.ON_CALL_REQUEST_FROM_CSMS)
    def handler_for_get_configuration(self, **kwargs):
        L.info(f"Preparing payload for GetConfiguration with {kwargs}")
        kwargs.update(
            {
                "HeartbeatInterval": self.heartbeat_interval,
                "MeterValuesSampledData": self.meter_values_interval,
                "MeterValueSampleInterval": self.meter_values_sample_data,
                "NumberOfConnectors": 1,
                "AuthorizeRemoteTxRequests": "false",
            }
        )
        return kwargs
