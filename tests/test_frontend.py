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


def test_price_plan_card_uses_ha_time_format_and_actual_history() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert 'locale.time_format === "24"' in source
    assert 'type: "history/history_during_period"' in source
    assert "Tegelikult ON" in source
    assert "möödunud OFF" in source


def test_price_plan_card_keeps_hour_labels_readable_with_horizontal_scroll() -> None:
    source = (
        Path(__file__).parents[1]
        / "custom_components/smart_energy_scheduler/frontend/smart-energy-scheduler-card.js"
    ).read_text()
    assert "hours.length * 34" in source
    assert 'style="width:${width}px"' in source
    assert ".hour-label{font-size:13px" in source
    assert "currentX - scroll.clientWidth / 2" in source
    assert "_initialScrollDone" in source
    assert 'class="y-axis"' in source
    assert ".y-axis{position:absolute;z-index:2;left:0;top:0;width:40px" in source
