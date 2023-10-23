from typing import Dict, List

from ocpp.v16.enums import Action
from structlog import get_logger

from utils import HandlerType, handler

L = get_logger(__name__)

DEFAULT_FIRMWARE = ""
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
        self.heartbeat_interval = 60
        self.meter_values_interval = 30
        self.meter_values_sample_data = ["Power.Active.Import"]
        self.configuration = {}

    @handler(Action.BootNotification, HandlerType.BEFORE_REQUEST)
    def payload_for_boot_notification(self, **kwargs):
        kwargs.update({"firmware": "virtual firmware 1.0.0"})
        return kwargs

    @handler(Action.StatusNotification, HandlerType.BEFORE_REQUEST)
    def payload_for_status_notification(self, **kwargs):
        return kwargs

    @handler(Action.StartTransaction, HandlerType.FOLLOW_REQUEST)
    def handler_for_start_transaction_response(self, payload):
        pass

    @handler(Action.ChangeConfiguration, HandlerType.ON_REQUEST)
    def handler_for_change_configuration(self, key: str, value: str):
        self.configuration[key] = value
        return True
