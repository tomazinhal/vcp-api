from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Union

from exceptions import NoModelImplementedError
from model_payload_factories.core import Core
from model_payload_factories.remote_trigger import RemoteTriggerFeature
from ocpp.messages import Call, CallError, CallResult, MessageType
from ocpp.v16.enums import Action, ChargePointErrorCode, ChargePointStatus
from structlog import get_logger
from utils import HandlerType, create_route_map

logger = get_logger(__name__)


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
class Charger(Core, RemoteTriggerFeature):
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
    supports_smart_charging: bool = False
    supports_remote_trigger: bool = True
    supports_firmware_management: bool = False
    supports_local_auth_management: bool = False
    supports_reservation: bool = False

    def __init__(
        self,
        charger_id: str,
        number_connectors: int,
        password: str | None = None,
        status: Optional[ChargePointStatus] = None,
        error: Optional[ChargePointErrorCode] = None,
    ):
        super().__init__()
        self.ready = False
        self.id = charger_id
        self.password = password
        self.number_connectors = number_connectors
        self.connectors = [Connector(i + 1) for i in range(number_connectors)]
        self.status = ChargePointStatus.available
        self.error = ChargePointErrorCode.no_error
        self.action_payload_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.BEFORE_CALL_REQUEST_FROM_CP
        )
        self.after_response_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.ON_CALL_RESPONSE_FROM_CSMS
        )
        self.on_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.ON_CALL_REQUEST_FROM_CSMS
        )
        self.follow_request_map: Dict[Action, Callable] = create_route_map(
            self, HandlerType.AFTER_CALL_RESPONSE_FROM_CP
        )
        self.call_message_id_to_action_map: Dict[str, Action] = {}
        logger.debug("Charger %s with %s connectors", self.id, self.number_connectors)

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
        logger.debug("Created empty Charger")
        return charger

    @classmethod
    def simple(cls):
        charger = cls("taf", 1)
        charger.ready = True
        return charger

    @classmethod
    def create(
        cls, charger_id: str, number_connectors: int, password: str | None = None
    ):
        charger = cls(charger_id, number_connectors, password=password)
        charger.ready = True
        return charger

    def create_data_for_payload(self, action, **kwargs):
        try:
            return self.action_payload_map[action](**kwargs)
        except KeyError:
            raise NoModelImplementedError(
                "Nothing to do from models side for %s", action
            )

    def handle_created_call(self, call: Call):
        logger.debug("Model handle call: %s", call)

    def handle_call_response(self, response: Union[Call, CallResult, CallError]):
        logger.debug("Model handle call response: %s", response)

    def handle_validated_call_response(
        self, response: Union[Call, CallResult, CallError]
    ):
        logger.debug("Model validate call response: %s", response)

    def receive_csms_call(self, message):
        try:
            self.on_request_map[message.action](message.payload)
        except (KeyError, NotImplementedError):
            logger.debug(f"Abstraction.{message.action}.on_request not implemented.")

    def after_cs_response(self, request: Call, response: Union[CallResult, CallError]):
        try:
            logger.debug(f"Checking abstraction.{request.action}.after_request.")
            return self.follow_request_map[request.action](request, response)
        except (KeyError, NotImplementedError):
            logger.debug(f"Abstraction.{request.action}.after_request not implemented.")
