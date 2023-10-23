"""
TriggerMessage
"""
from ocpp.exceptions import NotSupportedError
from ocpp.routing import on
from ocpp.v16.call_result import (
    ClearChargingProfilePayload,
    ClearChargingProfileStatus,
    GetCompositeSchedulePayload,
    GetCompositeScheduleStatus,
    SetChargingProfilePayload,
)
from ocpp.v16.enums import Action
from structlog import get_logger

L = get_logger(__name__)


class SmartChargingFeature:
    @on(Action.SetChargingProfile)
    def on_set_charging_profile(self, connector_id):
        if self.support_smart_charging:
            return SetChargingProfilePayload(status="Accepted")
        raise NotSupportedError()

    @on(Action.ClearChargingProfile)
    def on_clear_charging_profile(self):
        _ = ClearChargingProfilePayload(status=ClearChargingProfileStatus.accepted)
        raise NotSupportedError()

    @on(Action.GetCompositeSchedule)
    def on_get_composite_schedule(self):
        _ = GetCompositeSchedulePayload(status=GetCompositeScheduleStatus.accepted)
        raise NotSupportedError()
