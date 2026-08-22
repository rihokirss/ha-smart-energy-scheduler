"""Framework-independent data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any


@dataclass(frozen=True, slots=True)
class QuarterPrice:
    """One Nord Pool market interval in EUR/MWh."""

    start: datetime
    end: datetime
    market_eur_mwh: float


@dataclass(slots=True)
class HourPrice:
    """One local scheduler hour."""

    start: datetime
    end: datetime
    market_eur_mwh: float
    import_eur_mwh: float
    export_eur_mwh: float
    pv_wh: float = 0.0
    base_load_wh: float = 0.0

    @property
    def surplus_wh(self) -> float:
        """PV energy available to controlled loads."""
        return max(0.0, self.pv_wh - self.base_load_wh)


@dataclass(frozen=True, slots=True)
class TariffConfig:
    """Tariff inputs, all price values in EUR/MWh."""

    buy_margin: float
    sell_margin: float
    vat_fraction: float
    network_day: float
    network_night: float
    day_start: time
    day_end: time
    weekend_night: bool = True
    network_includes_vat: bool = False
    holiday_country: str | None = None


@dataclass(frozen=True, slots=True)
class PlanningDevice:
    """Inputs required by the pure planning engine."""

    device_id: str
    name: str
    nominal_power_w: float
    window_start: time
    window_end: time
    min_on_hours: int
    min_off_hours: int
    solar_priority: int
    always_on_below_eur_mwh: float | None = None
    always_off_above_eur_mwh: float | None = None


@dataclass(slots=True)
class PlannedHour:
    """One planned hour and its cost explanation."""

    start: datetime
    active: bool
    effective_eur_mwh: float
    import_eur_mwh: float
    export_eur_mwh: float
    allocated_solar_wh: float = 0.0
    reason: str = "price"


@dataclass(slots=True)
class DevicePlan:
    """A device plan across the available horizon."""

    device_id: str
    target_hours: dict[date, int]
    required_hours: dict[date, int] = field(default_factory=dict)
    apparent_temperatures: dict[date, float] = field(default_factory=dict)
    hours: list[PlannedHour] = field(default_factory=list)
    valid: bool = True
    error: str | None = None

    def active_at(self, moment: datetime) -> bool | None:
        """Return planned state for the hour containing moment."""
        for slot in self.hours:
            if slot.start.timestamp() <= moment.timestamp() < slot.start.timestamp() + 3600:
                return slot.active
        return None

    def as_dict(self) -> dict[str, Any]:
        """Serialize for storage and websocket clients."""
        return {
            "device_id": self.device_id,
            "target_hours": {key.isoformat(): value for key, value in self.target_hours.items()},
            "required_hours": {
                key.isoformat(): value for key, value in self.required_hours.items()
            },
            "apparent_temperatures": {
                key.isoformat(): round(value, 2)
                for key, value in self.apparent_temperatures.items()
            },
            "valid": self.valid,
            "error": self.error,
            "hours": [
                {
                    "start": hour.start.isoformat(),
                    "active": hour.active,
                    "effective_eur_mwh": round(hour.effective_eur_mwh, 4),
                    "import_eur_mwh": round(hour.import_eur_mwh, 4),
                    "export_eur_mwh": round(hour.export_eur_mwh, 4),
                    "allocated_solar_wh": round(hour.allocated_solar_wh, 1),
                    "reason": hour.reason,
                }
                for hour in self.hours
            ],
        }


@dataclass(slots=True)
class DeviceRuntimeState:
    """Mutable per-device runtime state."""

    enabled: bool = True
    override: str = "auto"
    override_until: datetime | None = None
    actual_hours_by_day: dict[str, float] = field(default_factory=dict)
    observation_source: str | None = None
    last_active: bool | None = None
    last_accounted_at: datetime | None = None
    next_transition: datetime | None = None
    reason: str = "initializing"
    locked_hour_start: datetime | None = None
    locked_active: bool | None = None
