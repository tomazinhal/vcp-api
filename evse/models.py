from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Union

from exceptions import NoModelImplementedError
from model_payload_factories.core import Core
from ocpp.messages import Call, CallError, CallResult
from ocpp.v16.enums import Action, ChargePointErrorCode, ChargePointStatus
from structlog import get_logger
from utils import HandlerType, create_route_map

L = get_logger(__name__)


@dataclass
class TransactionStatus(Enum):
    starting: 1
    ongoing: 2
    halted_by_ev: 3
    halted_by_cs: 4
    finishing: 5


@dataclass
class Transaction:
    id: int
    status: TransactionStatus
    meter_start: int
    meter_stop: int
    state_of_charge: int
    current_consumption: float
    current_offered: float
    # optional
    rfid: Optional[str]
    num_phases: Optional[int]

    def __init__(self, transaction_id: int):
        self.id = transaction_id
        self.status = TransactionStatus.started


@dataclass
class Connector:
    id: int
    status: ChargePointStatus
    # optional
    transaction: Optional[Transaction]
    error: Optional[ChargePointErrorCode]

    def __init__(self, connector_id):
        self.id = connector_id
        self.status = ChargePointStatus.available
        self.error = ChargePointErrorCode.no_error
        self.transaction = None


@dataclass
class Charger(Core):
    ready: bool
    """ready: whether the model is ready to be used for a handler"""
    id: str
    number_connectors: int
    connectors: list[Connector]
    status: ChargePointStatus
    error: Optional[ChargePointErrorCode]
    # configurations
    heartbeat_interval: int
    meter_values_interval: int
    meter_values_sample_data: List
    # features
    supports_core: bool = True
    supports_smart_charging: bool = True
    supports_remote_trigger: bool = False
    supports_firmware_management: bool = False
    supports_local_auth_management: bool = False
    supports_reservation: bool = False

    def __init__(
        self,
        charger_id: str,
        number_connectors: int,
        status: Optional[ChargePointStatus] = None,
        error: Optional[ChargePointErrorCode] = None,
    ):
        self.ready = False
        self.id = charger_id
        self.number_connectors = number_connectors
        self.connectors = [Connector(i + 1) for i in range(number_connectors)]
        self.status = ChargePointStatus.available
        self.error = ChargePointErrorCode.no_error
        self.heartbeat_interval = 60
        self.meter_values_interval = 30
        self.meter_values_sample_data = ["Power.Active.Import"]
        self.action_payload_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.CALL_FACTORY
        )
        self.response_handler_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.CALL_RESULT_PAYLOAD
        )
        L.debug("Charger %s with %s connectors", self.id, self.number_connectors)

    @classmethod
    def empty(cls):
        charger = Charger("", 0)
        charger.supports_core = False
        charger.supports_smart_charging = False
        charger.supports_remote_trigger = False
        charger.supports_firmware_management = False
        charger.supports_local_auth_management = False
        charger.supports_reservation = False
        charger.ready = False
        L.debug("Created empty Charger")
        return charger

    @classmethod
    def simple(cls):
        charger = cls("supercharger", 1)
        charger.ready = True
        return charger

    @classmethod
    def create(cls, charger_id: str, number_connectors: int):
        charger = cls(charger_id, number_connectors)
        charger.ready = True
        return charger

    def handle(self, msg: Union[Call, CallError, CallResult]):
        L.debug("Handling message %s", msg)

    def create_data_for_payload(self, action, **kwargs):
        L.debug("Action: %s", action)
        L.debug("Kwargs %s", kwargs)
        try:
            return self.action_payload_map[action](**kwargs)
        except KeyError:
            raise NoModelImplementedError(
                "Nothing to do from models side for %s", action
            )

    def handle_created_call(self, call: Call):
        L.debug("Call created: %s", call)

    def handle_call_response(self, response: Union[Call, CallResult, CallError]):
        L.debug("Response created: %s", response)

    def handle_validated_call_response(
        self, response: Union[Call, CallResult, CallError]
    ):
        action = response.action
        payload = response.payload
        try:
            return self.action_payload_map[action](payload)
        except KeyError:
            raise NoModelImplementedError(
                "Nothing to do from models side for %s", action
            )
        L.debug("response created: %s", response)
