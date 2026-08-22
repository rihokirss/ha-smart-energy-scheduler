"""Lightweight contract tests for the bundled Lovelace card."""

from pathlib import Path


def test_card_registers_and_uses_both_websocket_commands() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert 'customElements.define("smart-energy-scheduler-card"' in source
    assert "smart_energy_scheduler/get_plan" in source
    assert "smart_energy_scheduler/subscribe_plan" in source
    assert 'smart_energy_scheduler", "set_override' in source


def test_card_caps_horizon_at_48_hours() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert "Math.min(48" in source


def test_price_plan_card_colors_device_on_hours() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert 'customElements.define("smart-energy-price-plan-card"' in source
    assert "Planeeritud ON" in source
    assert 'active ? "#25a244" : "#f59e0b"' in source
    assert "_overlappingSlots(device, hour)" in source
    assert "segmentRect(slotStart, slotEnd" in source
    assert "new Date(slot.end" in source


def test_price_plan_card_uses_ha_time_format_and_actual_history() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert 'locale.time_format === "24"' in source
    assert 'type: "history/history_during_period"' in source
    assert "Tegelikult ON" in source
    assert "möödunud OFF" in source
    assert 'hourCycle: "h23"' in source


def test_price_plan_card_keeps_hour_labels_readable_with_horizontal_scroll() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert "hours.length * 17" in source
    assert 'style="width:${width}px"' in source
    assert ".hour-label{font-size:12px" in source
    assert "currentX - scroll.clientWidth / 2" in source
    assert "_centeredHourKey" in source
    assert "_scheduleHourCenter" in source
    assert "3600000 - Date.now() % 3600000" in source
    assert 'class="hour-label"' in source
    assert 'transform="rotate(-45' not in source
    assert 'class="y-axis"' in source
    assert ".y-axis{position:absolute;z-index:2;left:0;top:0;width:28px" in source
    assert "box-shadow:3px 0 5px" not in source
    assert "const left = 32, right = 8" in source
    assert "margin:var(--ha-space-3,12px) 0 0 -8px" in source


def test_timeline_cards_use_hour_only_labels_and_narrow_bars() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert "return this._formatHour(date);" in source
    assert "step * .86" in source
    assert "minmax(8px, 1fr)" in source
    assert ".chart,.blocks{display:grid;gap:2px;min-width:480px}" in source
    assert ".hour span{font-size:11px" in source


def test_scheduler_card_centers_current_hour_and_keeps_controls_visible() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert "_centerCurrentHour(hours)" in source
    assert "current.offsetLeft + current.offsetWidth / 2 - scroll.clientWidth / 2" in source
    assert ".device-head{display:flex;justify-content:flex-start" in source
    assert "position:sticky;left:0" in source
    assert "_planGradient(device, h)" in source
    assert "_plannedRanges(device, h)" in source


def test_price_plan_card_marks_current_hour_without_bar_outline() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert 'class="current-marker"' in source
    assert "Praegune tund" in source
    assert 'stroke-width="${current ? 3 : 0}"' not in source
    assert "tulba kõrgus: ostuhind" not in source
    assert "_formatDate" not in source
    assert 'class="date"' not in source


def test_heating_curve_card_is_editable_and_shows_forecast_points() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert 'customElements.define("smart-energy-heating-curve-card"' in source
    assert '"update_device_settings"' in source
    assert "apparent_temperatures" in source
    assert "required_hours" in source
    assert 'data-setting="${key}"' in source
    assert "<ha-slider" in source
    assert "<ha-switch" in source
    assert "<ha-button" in source
    assert "<button" not in source
    assert 'type="range"' not in source
    assert 'type="checkbox"' not in source
    assert ".chart{overflow:hidden" in source
    assert "min-width:560px" not in source
    assert 'class="axis-label"' in source
    assert ".axis-label{font-size:16px" in source
    assert "--ha-card-header-font-family" in source
    assert "--ha-card-header-font-size" in source
    assert '"always_on_below_eur_mwh"' in source
    assert '"always_off_above_eur_mwh"' in source
    assert '"Alati sees hinnaga kuni", 0, 1000' in source
    assert '"Alati väljas hinnaga alates", 0, 1000' in source
    assert 'data-choice-setting="planning_step_minutes"' in source
    assert 'data-planning-step="15"' in source
    assert 'data-planning-step="60"' in source
    assert '"planning_step_minutes", "Planeerimise samm", 15, 60, 45' not in source
    assert "15 min lubab algusi :00/:15/:30/:45" in source
    assert 'data-enable="${key}"' in source
    assert "Päeva miinimumtunnid võivad" in source
