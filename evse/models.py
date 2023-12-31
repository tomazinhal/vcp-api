from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Union

from ocpp.messages import Call, CallError, CallResult
from ocpp.v16.enums import Action, ChargePointErrorCode, ChargePointStatus
from structlog import get_logger

from exceptions import NoModelImplementedError
from model_payload_factories.core import Core
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
    configuration: Dict
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
        super().__init__()
        self.ready = False
        self.id = charger_id
        self.number_connectors = number_connectors
        self.connectors = [Connector(i + 1) for i in range(number_connectors)]
        self.status = ChargePointStatus.available
        self.error = ChargePointErrorCode.no_error
        self.before_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.BEFORE_REQUEST
        )
        self.follow_up_handler_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.FOLLOW_REQUEST
        )
        self.on_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.ON_REQUEST
        )
        self.after_response_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.AFTER_RESPONSE
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
        charger = cls("taf", 1)
        charger.ready = True
        return charger

    @classmethod
    def create(cls, charger_id: str, number_connectors: int):
        charger = cls(charger_id, number_connectors)
        charger.ready = True
        return charger

    def on_request_handle(self, msg: Union[Call, CallError, CallResult]):
        L.debug("on_request_handle message %s", msg)
        try:
            return self.on_request_map[msg.action](msg.payload)
        except KeyError:
            raise NoModelImplementedError(
                "Nothing to do from models side for %s", msg.action
            )

    def follow_up_handle(
        self,
        msg: Union[Call, CallError, CallResult],
        response: Union[CallError, CallResult, None],
    ):
        L.debug("follow_up_handle message %s", msg)
        try:
            return self.follow_up_handler_map[msg.action](msg.payload)
        except KeyError:
            L.debug(f"Abstraction does not 'follow' handle {msg.action}")

    def create_data_for_payload(self, action, **kwargs):
        L.debug("Action: %s", action)
        L.debug("Kwargs %s", kwargs)
        try:
            return self.before_request_map[action](**kwargs)
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
            return self.before_request_map[action](payload)
        except KeyError:
            raise NoModelImplementedError(
                "Nothing to do from models side for %s", action
            )
