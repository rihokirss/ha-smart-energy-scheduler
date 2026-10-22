"""Runtime cycle tracking across a briefly unavailable device source."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("homeassistant")

from custom_components.smart_energy_scheduler.coordinator import SmartEnergyCoordinator
from custom_components.smart_energy_scheduler.models import DeviceRuntimeState

TALLINN = ZoneInfo("Europe/Tallinn")


def test_unavailable_source_during_restart_does_not_restart_cycle() -> None:
    started = datetime(2026, 10, 22, 18, 56, tzinfo=TALLINN)
    coordinator = SmartEnergyCoordinator.__new__(SmartEnergyCoordinator)
    coordinator.timezone = TALLINN
    coordinator.entry = SimpleNamespace(
        get_subentries_of_type=lambda _type: [SimpleNamespace(subentry_id="pump")]
    )
    coordinator.states = {
        "pump": DeviceRuntimeState(
            last_active=True,
            last_accounted_at=started,
            cycle_started_at=started,
            cycle_active=True,
        )
    }
    observations = iter([None, True])
    coordinator._observed_active = lambda _subentry: next(observations)

    async def save_state() -> None:
        return None

    coordinator.async_save_state = save_state

    asyncio.run(coordinator.async_account_actual(started + timedelta(hours=1, minutes=27)))
    asyncio.run(coordinator.async_account_actual(started + timedelta(hours=1, minutes=28)))

    state = coordinator.states["pump"]
    assert state.cycle_active is True
    assert state.cycle_started_at == started
