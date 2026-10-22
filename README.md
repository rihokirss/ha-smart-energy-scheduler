# Smart Energy Scheduler for Home Assistant

[![Validate](https://github.com/rihokirss/ha-smart-energy-scheduler/actions/workflows/validate.yml/badge.svg)](https://github.com/rihokirss/ha-smart-energy-scheduler/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://www.hacs.xyz/)
[![Home Assistant 2026.8+](https://img.shields.io/badge/Home%20Assistant-2026.8%2B-18BCF2.svg)](https://www.home-assistant.io/)

Smart Energy Scheduler is a custom Home Assistant integration that schedules heat pumps,
water heaters, EV charging permits, and other switch-like loads when electricity is most
favorable.

It combines Nord Pool Day-Ahead prices, import and export fees, network tariffs,
Forecast.Solar production, house base load, and optional weather compensation into a
rolling 48-hour plan. Each configured load remains an ordinary Home Assistant entity and
can be monitored or overridden from the generated entities or the bundled Lovelace cards.

> [!CAUTION]
> This integration can send real `turn_on` and `turn_off` commands. Keep **shadow mode**
> enabled until the tariff model, device feedback, failure behavior, and generated plans
> have been verified for your installation.

## Features

- Rolling 48-hour planning using Nord Pool Day-Ahead prices.
- Independent schedules for multiple switch-like loads.
- 15-minute or 60-minute device start intervals.
- Daily base, minimum, and maximum runtime constraints.
- Minimum consecutive ON and OFF durations.
- Optional effective-price thresholds for always-ON and always-OFF behavior.
- Weather-compensated runtime targets for heating loads.
- Forecast.Solar support through the Home Assistant Energy Dashboard.
- Shared PV allocation by device priority without double-counting production.
- Seasonal sunrise/sunset fallback when a solar forecast is unavailable.
- Optional winter period that plans without PV, for example 15 October – 15 February.
- VAT, purchase/sale margins, day/night tariffs, weekends, and public holidays.
- Shadow mode, explicit failure modes, output inversion, and timed manual overrides.
- Generated sensors, controls, services, WebSocket updates, and three Lovelace cards.
- English and Estonian configuration translations.

## Requirements

| Requirement | Purpose |
| --- | --- |
| Home Assistant 2026.8.0 or newer | Config subentries and the current data-entry-flow APIs |
| A Nord Pool integration providing `nordpool.hourly` | Day-Ahead market prices |
| A `switch`, `input_boolean`, or `light` target | The controlled load or its run permit |
| An hourly `weather` entity (optional) | Weather-compensated runtime |
| Forecast.Solar configured in the Energy Dashboard (optional) | PV production forecast |

The integration currently expects the Nord Pool service response to contain quarter-hour
price intervals. Tomorrow's prices are optional until the provider has published a complete
local day.

## Installation

### HACS custom repository

Until the repository is included in the HACS default catalog:

1. Open **HACS → Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/rihokirss/ha-smart-energy-scheduler` with category
   **Integration**.
4. Search for **Smart Energy Scheduler** and install it.
5. Restart Home Assistant.

### Manual installation

1. Download or clone this repository.
2. Copy `custom_components/smart_energy_scheduler` to
   `<config>/custom_components/smart_energy_scheduler` on the Home Assistant host.
3. Restart Home Assistant.

The final directory should contain at least:

```text
<config>/custom_components/smart_energy_scheduler/
├── __init__.py
├── config_flow.py
├── manifest.json
├── services.yaml
├── strings.json
├── translations/
└── frontend/
```

## Initial setup

1. Open **Settings → Devices & services → Add integration**.
2. Search for **Smart Energy Scheduler**.
3. Review the imported tariff defaults and confirm that they match your contract.
4. Select an hourly weather entity if weather compensation will be used.
5. Leave **shadow mode** enabled.
6. Finish the setup, open the generated device row, and choose **Configure device**.
7. Select the correct target and review every device section before enabling control.

Only one scheduler config entry is supported. Additional controlled loads are created as
config subentries from **Add controlled device** on the integration page.

### Shared settings

The integration-level **Configure** action contains settings shared by every load:

- Nord Pool area and currency;
- purchase and sale margins;
- VAT and whether network fees already include VAT;
- day and night network fees and tariff times;
- weekend and public-holiday night tariff behavior;
- weather entity and house base load;
- solar fallback season and sunrise/sunset offsets;
- optional winter period in which PV production is ignored;
- optional grid/PV power sensors used for diagnostics;
- shadow mode and tariff confirmation.

### Device settings

Each controlled load has six compact configuration sections:

| Section | Settings |
| --- | --- |
| Device | Name, target entity, inverted output, automatic control |
| Schedule and daily hours | Work window, base/min/max hours, planning step, minimum ON/OFF durations |
| Power and measurement | Feedback entity, power sensor, multiplier, nominal power |
| Price limits | Optional always-ON and always-OFF effective prices |
| Weather-based control | Weather adjustment, reference temperature, curve slope, forecast window and lead |
| Advanced behavior | Solar priority and missing-data failure mode |

When the start and end of the work window are equal, the device is allowed to run all day.
A 15-minute planning step permits starts at `:00`, `:15`, `:30`, and `:45`; a 60-minute
step permits starts only at `:00`. Minimum ON/OFF durations are not shortened by the finer
planning step.

## Data sources and calculation model

### Electricity prices

The effective import price for each market interval is calculated as:

```text
(market price + purchase margin) × (1 + VAT) + applicable network fee
```

If **network fees include VAT** is enabled, VAT is not added to the network component.
The export value is:

```text
market price + sale margin
```

Every quarter-hour is tariffed using its own local timestamp. The implementation preserves
23-, 24-, and 25-hour local days, including the repeated hour at the end of daylight-saving
time. A missing or incomplete next day does not invalidate the current day's plan; the
integration retries on its next update.

### Solar forecast

Smart Energy Scheduler reads the same solar forecast providers selected under
**Settings → Dashboards → Energy → Solar production**. Installing Forecast.Solar alone is
not sufficient: its config entry must be selected as a forecast provider for the Energy
Dashboard solar source.

When several forecast providers are selected, their hourly `wh_hours` series are summed.
Forecast PV first covers the configured house base load. Remaining PV is allocated once to
controlled devices in solar-priority order, so the same production is never assigned to two
loads. Self-consumed PV is valued at the export revenue that would otherwise have been
earned.

If all providers are missing or fail, the optional fallback can model solar availability
between configurable sunrise/sunset offsets and months. Outside that fallback window,
forecast production is zero and price-only planning continues with a warning. The optional
PV power sensor is diagnostic only; it is not used as a forecast source.

The optional **winter period** ignores both forecast and fallback PV on every local day
between the configured first and last month/day, inclusive. The range may wrap the new
year, so `10/15` to `2/15` covers 15 October through 15 February. While the whole planning
horizon is inside the winter period, the solar forecast is not requested at all and the
cards show *PV talvel arvestamata*. The house base load and price-only planning are
unchanged.

### Weather compensation

For weather-controlled devices, the daily target is:

```text
base hours + (reference temperature − forecast apparent temperature) × hours per degree
```

The result is rounded and clamped to the configured minimum and maximum. The forecast value
is averaged across a configurable look-ahead window, which can be shifted into the future
with the preheat/thermal-inertia setting.

The legacy mode calculates wind chill from forecast temperature and wind speed. When legacy
mode is disabled, the provider's `apparent_temperature` is preferred; plain temperature is
used only when apparent temperature is unavailable.

### Price limits

- **Always ON at or below** may expand the daily target when the complete minimum run is
  sufficiently cheap.
- **Always OFF at or above** rejects expensive candidate runs, but the configured daily
  minimum remains a safety requirement and can override that cap.
- The always-ON value must be lower than the always-OFF value when both are enabled.

## Safety and output behavior

- **Shadow mode** calculates and publishes plans without sending target commands.
- The integration uses explicit `homeassistant.turn_on` and `homeassistant.turn_off` calls;
  it never uses `toggle`.
- **Inverted output** means a scheduled active interval sends `turn_off` to the target.
- The automatic-control switch can disable commands for an individual load.
- Missing source data can be configured to force ON, force OFF, or keep the current state.
- Unloading the integration does not change the physical target state.
- Actual runtime is observed from the power sensor first, then the feedback entity, and
  finally the target entity.

Before leaving shadow mode:

1. Observe at least two complete days, including tomorrow-price publication.
2. Compare planned activity with the device's actual feedback or power history.
3. Verify tariff units: all price and fee fields are in `EUR/MWh`.
4. Test inverted output and manual overrides with a non-critical target.
5. Confirm the selected failure mode is safe during a Home Assistant or data-provider
   outage.

## Entities

Every controlled device creates the following Home Assistant entities:

| Platform | Entity purpose |
| --- | --- |
| `binary_sensor` | Whether the current interval is scheduled active |
| `switch` | Enable or disable automatic control for the device |
| `select` | Automatic, forced ON, or forced OFF override |
| `datetime` | Optional override expiration time |
| `number` | Base/min/max hours and weather-curve controls |
| `sensor` | Planned, actual, and remaining hours; next transition; control reason |

The integration stores runtime counters and overrides in Home Assistant storage and restores
them after restart.

## Lovelace cards

The integration serves its bundled JavaScript at:

```text
/smart_energy_scheduler/smart-energy-scheduler-card.js
```

Add that URL under **Settings → Dashboards → Resources** as a **JavaScript module**. Then
add one or more manual cards.

### Complete multi-device plan

```yaml
type: custom:smart-energy-scheduler-card
title: Energy scheduling
hours: 48
```

This card displays market prices, PV production, every device plan, shadow/live status, and
two-hour ON/OFF overrides.

### Price and activity chart

```yaml
type: custom:smart-energy-price-plan-card
title: Price and heat-pump plan
target_entity: switch.heat_pump
hours: 48
```

The chart combines historical activity, future 15/60-minute plan segments, import price,
effective device price, and forecast PV.

### Editable heating curve

```yaml
type: custom:smart-energy-heating-curve-card
title: Heat-pump heating curve
target_entity: switch.heat_pump
min_temperature: -25
max_temperature: 25
```

Per-device cards can select a load with `device_id`, `device` (configured name), or
`target_entity`. If no selector is supplied, the first configured device is used.

## Services

| Service | Description |
| --- | --- |
| `smart_energy_scheduler.recalculate` | Fetch inputs, rebuild the plan, and apply the current interval |
| `smart_energy_scheduler.set_override` | Set a device to automatic, forced ON, or forced OFF mode |
| `smart_energy_scheduler.update_device_settings` | Update heating-curve, planning-step, and price-limit settings |

Example manual override:

```yaml
action: smart_energy_scheduler.set_override
data:
  device_id: 01EXAMPLEDEVICEID
  mode: "on"
  until: "2026-01-15 14:00:00"
```

The internal scheduler device ID is visible in service calls generated by the bundled card
and in the `smart_energy_scheduler/get_plan` WebSocket response. Most users should use the
generated override select instead of calling the service directly.

## Troubleshooting

### The plan is unavailable

- Confirm that `nordpool.hourly` exists under **Developer tools → Actions**.
- Call `smart_energy_scheduler.recalculate` and inspect the integration log.
- A partial next day is normal; unavailable current-day prices are not.
- Check the device's **Control reason** sensor and the warnings shown on the cards.

### Forecast.Solar is installed but PV stays at zero

- Open the Energy Dashboard configuration.
- Edit the solar production source.
- Select each Forecast.Solar entry under solar forecast providers.
- Recalculate the scheduler plan.

### Weather compensation has no effect

- Select a weather entity in the integration-level configuration.
- Confirm that the entity provides an hourly forecast.
- Enable weather adjustment in the device's **Weather-based control** section.
- Review fallback warnings on the Lovelace card.

### A Lovelace card does not update

- Verify that the resource URL is registered as a JavaScript module.
- Hard-refresh the browser after updating the integration.
- Confirm that the integration is loaded and the resource URL returns JavaScript.

## Updating

For HACS installations, update from HACS and restart Home Assistant. For manual
installations, replace the complete integration directory and restart Home Assistant. Do
not copy only selected Python files because translations and the bundled frontend
may change together.

## Development

Create a virtual environment and install the test dependencies:

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
```

Run the local checks:

```bash
.venv/bin/ruff check .
.venv/bin/pytest
```

GitHub Actions additionally runs Home Assistant `hassfest` and HACS validation. Pull
requests should keep the stored config-entry format backward compatible or provide an
explicit migration.

## Project status

This project is under active development. Treat it as pre-release automation software and
validate every plan in shadow mode before allowing it to control equipment. Bug reports and
focused pull requests are welcome through the GitHub issue tracker.

## License

Released under the [MIT License](LICENSE).
