# Smart Energy Scheduler

Home Assistant 2026.8+ custom integration for scheduling heat pumps and other switch-like loads against Nord Pool Day-Ahead prices, network tariffs, Forecast.Solar production, house base load, and apparent-temperature forecasts.

The first configured device is the current heat pump target `switch.sonoff_1001208b81_1`. It is non-inverted, uses a 9 h base target, 3–24 h limits, and forces active when price data is unavailable. The integration starts in **shadow mode** and therefore issues no commands until explicitly enabled in the integration settings.

## Installation

1. Copy `custom_components/smart_energy_scheduler` into Home Assistant's `config/custom_components` directory (or install the repository as a HACS custom integration).
2. Restart Home Assistant.
3. Add **Smart Energy Scheduler** from Settings → Devices & services.
4. Verify the tariff values and select `weather.openweathermap` (or another hourly forecast entity).
5. Add this Lovelace resource as a JavaScript module:

   `/smart_energy_scheduler/smart-energy-scheduler-card.js`

6. Add a manual dashboard card:

```yaml
type: custom:smart-energy-scheduler-card
title: Energia juhtimine
hours: 48
```

For a price graph matching a conventional daily tariff chart, starting at local
midnight, with actual past activity and future planned activity:

```yaml
type: custom:smart-energy-price-plan-card
title: Hind ja tööplaan
target_entity: switch.sonoff_1001208b81_1
hours: 48
```

Editable weather response and heating curve:

```yaml
type: custom:smart-energy-heating-curve-card
title: Soojuspumba küttekõver
target_entity: switch.sonoff_1001208b81_1
```

The same per-device card also edits two optional effective-price limits. “Always ON” can
expand that device's daily target when the tariff-, VAT-, and PV-adjusted price is cheap.
“Always OFF” caps the weather-derived target when the effective price is expensive, while
the configured daily minimum remains a safety requirement and may override that cap.

Past hours are dark green when HA history shows actual activity and grey when off.
Future planned hours are green for ON and orange for OFF. The blue line is the
device's effective price after forecast solar allocation. The current bar has an
outline showing whether feedback says the device is actually active. The x-axis
uses local whole-hour labels (`00`–`23`) in the Home Assistant time zone.

Keep shadow mode enabled for at least 48 hours. Compare the plan with actual conditions before enabling output control.

## Configuration layout

- **Settings → Devices & services → Smart Energy Scheduler → Configure** contains the shared price, tax, network tariff, PV/base-load, weather-source, and shadow-mode settings.
- **Settings → Devices & services → Smart Energy Scheduler → device row → Configure device** contains that device's target entity, inverted-output setting, feedback/power sensors, work window, daily hours, minimum ON/OFF times, weather adjustment, and failure behavior.
- Use **Add controlled device** in the integration menu to create another independently scheduled target. Shared price and tariff settings are not duplicated per device.

## Pricing model

- Import with VAT-inclusive network fees: `(market + purchase margin) × (1 + VAT) + slot-specific network fee`
- Export: `market + sale margin`
- Forecast PV first covers configured house base load. Remaining energy is allocated once, by device solar priority.
- Self-consumed PV is valued at the export revenue that would otherwise have been earned.
- If Forecast.Solar is unavailable, the default fallback reproduces the previous YAML model: March–September, from three hours after sunrise until two hours before sunset. During that window the base load and configured controlled loads are treated as solar-covered. All fallback parameters are shared settings.
- Outside the fallback window a missing PV forecast is treated as zero production; price-based planning remains valid and a warning is exposed.

Every 15-minute price is tariffed using its own timestamp and then duration-weighted into absolute one-hour cycles. This preserves both repeated hours on the 25-hour DST day.

The default Estonian Elektrilevi **Võrk 2** values are 75.30 EUR/MWh by day
and 43.50 EUR/MWh by night, already including VAT. The default VAT rate is
24%. Day pricing applies Monday–Friday 07:00–22:00; nights, weekends, and
Estonian public holidays use the night rate. A toggle allows VAT-exclusive
network prices for other tariffs without changing the calculation model.

Tomorrow's prices are optional until Nord Pool has published a complete local
23/24/25-hour day. A missing, delayed, or partial next-day response does not
invalidate today's schedule; the integration retries on every 15-minute update.

## Weather model

Daily target: `base + (reference apparent temperature − rolling forecast apparent temperature) × hours per degree`, clamped to minimum/maximum and rounded to whole hours. The default rolling window is the next 12 hours, matching the intent of the previous YAML model that sampled forecast hours 0/3/7/11. A configurable forecast lead shifts that window further forward for a high-inertia building. The heat-pump default reproduces the previous YAML wind-chill formula from forecast temperature and wind speed; this can be switched to the weather provider's own `apparent_temperature` from the heating-curve card. Plain temperature is used only as a visible fallback.

## Cutover checklist

- Observe shadow mode for 48 hours.
- Verify Sonoff restore/power-on behavior for a complete HA outage.
- Disable `Soojuspump`, `Soojuspumba automaatjuhtimine`, and `Soojuspumba kesköine kontroll` only when leaving shadow mode.
- Stop the Shelly `Heating 24h-Forecast` script and watchdog at the same cutover.
- Retain the old YAML for seven stable days and until the radiator-pump dependency on `binary_sensor.pumba_taimer` is migrated.
- Remove the temporary `gpt` admin account or its admin right and rotate the shared password.

## Development

```bash
python -m pip install -e '.[test]'
pytest
ruff check .
```
