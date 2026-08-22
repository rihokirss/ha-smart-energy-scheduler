"""Plan status sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import SmartEnergyConfigEntry
from .entity import SchedulerEntity


@dataclass(frozen=True, kw_only=True)
class SchedulerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SchedulerStatusSensor], Any]


def _today(entity: SchedulerStatusSensor) -> str:
    return dt_util.now().astimezone(entity.coordinator.timezone).date().isoformat()


def _remaining(entity: SchedulerStatusSensor) -> float:
    """Return scheduled hours still ahead in today's plan."""
    plan = entity.coordinator.data.plans.get(entity.device_id) if entity.coordinator.data else None
    if not plan:
        return 0.0
    today = _today(entity)
    return float(sum(hour.active for hour in plan.hours if hour.start.date().isoformat() == today))


def _actual(entity: SchedulerStatusSensor) -> float:
    """Return observed active time today."""
    return round(entity.runtime_state.actual_hours_by_day.get(_today(entity), 0.0), 2)


def _planned(entity: SchedulerStatusSensor) -> float:
    """Return the expected whole-day total: actual plus scheduled remainder."""
    return float(round(_actual(entity) + _remaining(entity)))


DESCRIPTIONS = (
    SchedulerSensorDescription(
        key="planned_hours",
        translation_key="planned_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:calendar-clock",
        value_fn=_planned,
    ),
    SchedulerSensorDescription(
        key="actual_hours",
        translation_key="actual_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:progress-clock",
        value_fn=_actual,
    ),
    SchedulerSensorDescription(
        key="remaining_hours",
        translation_key="remaining_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-sand",
        value_fn=_remaining,
    ),
    SchedulerSensorDescription(
        key="next_transition",
        translation_key="next_transition",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:timeline-clock",
        value_fn=lambda entity: entity.runtime_state.next_transition,
    ),
    SchedulerSensorDescription(
        key="reason",
        translation_key="reason",
        icon="mdi:information-outline",
        value_fn=lambda entity: entity.runtime_state.reason,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.runtime_data.device_subentries:
        async_add_entities(
            [
                SchedulerStatusSensor(entry.runtime_data, entry, subentry, description)
                for description in DESCRIPTIONS
            ],
            config_subentry_id=subentry.subentry_id,
        )


class SchedulerStatusSensor(SchedulerEntity, SensorEntity):
    """One calculated scheduler status value."""

    entity_description: SchedulerSensorDescription

    def __init__(self, coordinator, entry, subentry, description) -> None:
        super().__init__(coordinator, entry, subentry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self)
