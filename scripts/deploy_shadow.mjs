#!/usr/bin/env node
/** Deploy only the integration files through the official File editor ingress API. */

import { readFile, readdir } from "node:fs/promises";
import { join, relative } from "node:path";

const baseUrl = (process.env.HA_URL || "http://192.168.0.200:8123").replace(/\/$/, "");
const clientId = process.env.HA_CLIENT_ID || "http://localhost/";
const username = process.env.HA_USER;
const password = process.env.HA_PASSWORD;
if (!username || !password) throw new Error("Set HA_USER and HA_PASSWORD");

const flowResponse = await fetch(`${baseUrl}/auth/login_flow`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ client_id: clientId, handler: ["homeassistant", null], redirect_uri: clientId }),
});
if (!flowResponse.ok) throw new Error(`HA login flow failed (${flowResponse.status})`);
const flow = await flowResponse.json();
const loginResponse = await fetch(`${baseUrl}/auth/login_flow/${flow.flow_id}`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ client_id: clientId, username, password }),
});
if (!loginResponse.ok) throw new Error(`HA credentials failed (${loginResponse.status})`);
const login = await loginResponse.json();
if (!login.result) throw new Error(`HA credentials were not accepted (${login.type || "unknown"})`);
const tokenResponse = await fetch(`${baseUrl}/auth/token`, {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ grant_type: "authorization_code", code: login.result, client_id: clientId }),
});
if (!tokenResponse.ok) throw new Error(`HA token exchange failed (${tokenResponse.status})`);
const { access_token: accessToken } = await tokenResponse.json();

const socket = new WebSocket(`${baseUrl.replace(/^http/, "ws")}/api/websocket`);
let nextId = 1;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "auth_required") {
    socket.send(JSON.stringify({ type: "auth", access_token: accessToken }));
  } else if (message.type === "result" && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.success) resolve(message.result);
    else reject(new Error(JSON.stringify(message.error)));
  }
});
await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error("WebSocket authentication timeout")), 10000);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "auth_ok") {
      clearTimeout(timeout);
      resolve();
    } else if (message.type === "auth_invalid") {
      clearTimeout(timeout);
      reject(new Error("WebSocket authentication failed"));
    }
  });
});

function wsRequest(payload) {
  const id = nextId++;
  const message = { id, ...payload };
  socket.send(JSON.stringify(message));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

function supervisor(endpoint, method = "get", data = undefined) {
  const payload = { type: "supervisor/api", endpoint, method };
  if (data !== undefined) payload.data = data;
  return wsRequest(payload);
}

const sessionResult = await supervisor("/ingress/session", "post", {});
const session = sessionResult.session || sessionResult;
if (typeof session !== "string") throw new Error("Supervisor returned no ingress session");
const addonInfo = await supervisor("/addons/core_configurator/info");
const ingressEntry = addonInfo.ingress_entry || addonInfo.data?.ingress_entry;
if (typeof ingressEntry !== "string") throw new Error("File editor has no ingress entry");
const ingress = `${baseUrl}${ingressEntry.replace(/\/$/, "")}`;

async function postForm(path, values, allowExists = false) {
  const response = await fetch(`${ingress}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Cookie: `ingress_session=${session}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams(values),
  });
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); } catch { body = { error: !response.ok, message: text }; }
  if (!response.ok || (body.error && !(allowExists && /exist/i.test(body.message || "")))) {
    throw new Error(`${path}: ${response.status} ${body.message || text}`);
  }
  return body;
}

const remoteRoot = "/homeassistant/custom_components/smart_energy_scheduler";
for (const [path, name] of [
  ["/homeassistant", "custom_components"],
  ["/homeassistant/custom_components", "smart_energy_scheduler"],
  [remoteRoot, "frontend"],
  [remoteRoot, "translations"],
]) {
  await postForm("/api/newfolder", { path, name }, true);
}

const localRoot = new URL("../custom_components/smart_energy_scheduler/", import.meta.url).pathname;
async function filesIn(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const result = [];
  for (const entry of entries) {
    if (entry.name === "__pycache__") continue;
    const full = join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await filesIn(full));
    else result.push(full);
  }
  return result;
}

const files = await filesIn(localRoot);
for (const file of files) {
  const target = `${remoteRoot}/${relative(localRoot, file)}`;
  await postForm("/api/save", { filename: target, text: await readFile(file, "utf8") });
}

const check = await supervisor("/core/check", "post", {});
let configFlow = null;
if (process.env.HA_VERIFY === "1" || process.env.HA_CONFIGURE_SHADOW === "1") {
  const flowResponse = await fetch(`${baseUrl}/api/config/config_entries/flow`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ handler: "smart_energy_scheduler", show_advanced_options: true }),
  });
  const flow = await flowResponse.json();
  if (!flowResponse.ok || flow.type === "abort") {
    throw new Error(`Config flow verification failed: ${JSON.stringify(flow.errors || flow.reason || flow)}`);
  }
  configFlow = { type: flow.type, step_id: flow.step_id, errors: flow.errors };
  if (process.env.HA_CONFIGURE_SHADOW === "1") {
    const completeResponse = await fetch(
      `${baseUrl}/api/config/config_entries/flow/${flow.flow_id}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          area: "EE",
          currency: "EUR",
          buy_margin: 2.44,
          sell_margin: -4.5,
          vat: 22,
          network_day: 36.9,
          network_night: 21,
          day_start: "07:00:00",
          day_end: "22:00:00",
          weekend_night: true,
          weather_entity: "weather.openweathermap",
          base_load_w: 500,
          grid_power_sensor: "sensor.filtered_peaarvesti_maja_current_power",
          shadow_mode: true,
          tariff_confirmed: true,
        }),
      },
    );
    const completed = await completeResponse.json();
    if (!completeResponse.ok || completed.type !== "create_entry") {
      throw new Error(`Shadow setup failed: ${JSON.stringify(completed.errors || completed)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 4000));
    const plan = await wsRequest({ type: "smart_energy_scheduler/get_plan" });
    const first = Array.isArray(plan) ? plan[0] : plan;
    configFlow = {
      type: completed.type,
      title: completed.title,
      plan_ready: Boolean(first && !first.error && first.hours?.length),
      plan_hours: first?.hours?.length || 0,
      plan_error: first?.error || null,
      warnings: first?.warnings || [],
    };
  }
}
let inspection = null;
if (process.env.HA_INSPECT === "1") {
  const haConfigResponse = await fetch(`${baseUrl}/api/config`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const haConfig = haConfigResponse.ok ? await haConfigResponse.json() : {};
  const schedulerEntries = await wsRequest({
    type: "config_entries/get",
    domain: "smart_energy_scheduler",
  });
  const plans = await wsRequest({ type: "smart_energy_scheduler/get_plan" });
  const plan = Array.isArray(plans) ? plans[0] : plans;
  let targetHistory = {};
  if (plan?.hours?.[0]?.start) {
    targetHistory = await wsRequest({
      type: "history/history_during_period",
      start_time: new Date(plan.hours[0].start).toISOString(),
      end_time: new Date().toISOString(),
      entity_ids: ["switch.sonoff_1001208b81_1"],
      minimal_response: true,
      no_attributes: true,
    }).catch(() => ({}));
  }
  const registry = await wsRequest({ type: "config/entity_registry/list" });
  const allStates = await wsRequest({ type: "get_states" });
  const temperatureCandidates = allStates
    .filter((state) => /gaas|vesi/i.test(`${state.entity_id} ${state.attributes.friendly_name || ""}`))
    .map((state) => ({
      entity_id: state.entity_id,
      name: state.attributes.friendly_name,
      state: state.state,
      unit: state.attributes.unit_of_measurement,
    }));
  const controlCandidates = allStates
    .filter((state) => /shelly|sonoff|soojus|pump|heating|sv_/i.test(
      `${state.entity_id} ${state.attributes.friendly_name || ""}`,
    ))
    .filter((state) => ["switch", "input_boolean", "binary_sensor", "climate", "select"].includes(
      state.entity_id.split(".")[0],
    ))
    .map((state) => ({
      entity_id: state.entity_id,
      name: state.attributes.friendly_name,
      state: state.state,
    }));
  let temperatureHistory = {};
  const temperatureHistoryHours = Number(process.env.TEMP_HISTORY_HOURS || 24);
  if (temperatureCandidates.length) {
    temperatureHistory = await wsRequest({
      type: "history/history_during_period",
      start_time: new Date(Date.now() - temperatureHistoryHours * 3600000).toISOString(),
      end_time: new Date().toISOString(),
      entity_ids: temperatureCandidates.map((state) => state.entity_id),
      minimal_response: true,
      no_attributes: true,
    }).catch(() => ({}));
  }
  const temperatureHistorySummary = Object.fromEntries(
    temperatureCandidates.map((candidate) => {
      const values = (temperatureHistory[candidate.entity_id] || [])
        .map((item) => Number(item.s ?? item.state))
        .filter(Number.isFinite);
      return [candidate.entity_id, {
        samples: values.length,
        minimum: values.length ? Math.min(...values) : null,
        maximum: values.length ? Math.max(...values) : null,
        recent: values.slice(-12),
      }];
    }),
  );
  function numericSeries(entityId) {
    return (temperatureHistory[entityId] || [])
      .map((item) => ({
        time: Number(item.lu ?? item.lc) * 1000 || Date.parse(item.last_changed || ""),
        value: Number(item.s ?? item.state),
      }))
      .filter((item) => Number.isFinite(item.time) && Number.isFinite(item.value))
      .sort((left, right) => left.time - right.time);
  }
  function sampledDeltas(firstId, secondId) {
    const first = numericSeries(firstId);
    const second = numericSeries(secondId);
    if (!first.length || !second.length) return [];
    const result = [];
    let firstIndex = 0;
    let secondIndex = 0;
    const start = Date.now() - temperatureHistoryHours * 3600000;
    for (let stamp = start; stamp <= Date.now(); stamp += 5 * 60000) {
      while (firstIndex + 1 < first.length && first[firstIndex + 1].time <= stamp) firstIndex++;
      while (secondIndex + 1 < second.length && second[secondIndex + 1].time <= stamp) secondIndex++;
      if (first[firstIndex].time <= stamp && second[secondIndex].time <= stamp) {
        result.push(Number((first[firstIndex].value - second[secondIndex].value).toFixed(2)));
      }
    }
    return result;
  }
  function summarizeDeltas(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const quantile = (ratio) => sorted[Math.min(sorted.length - 1, Math.floor(ratio * sorted.length))];
    return {
      samples: values.length,
      min: sorted[0],
      p10: quantile(.1),
      median: quantile(.5),
      p90: quantile(.9),
      max: sorted.at(-1),
      minutes_above: Object.fromEntries([3, 5, 8, 10, 15].map((level) => [level, values.filter((value) => value > level).length * 5])),
      recent: values.slice(-18),
    };
  }
  const temperatureDeltaAnalysis = {
    gas_supply_minus_gas_return: summarizeDeltas(sampledDeltas(
      "sensor.sv_gaas_peale_temperature", "sensor.sv_gaas_maha_temperature",
    )),
    gas_supply_minus_water_supply: summarizeDeltas(sampledDeltas(
      "sensor.sv_gaas_peale_temperature", "sensor.sv_vesi_peale_temperature",
    )),
    water_supply_minus_water_return: summarizeDeltas(sampledDeltas(
      "sensor.sv_vesi_peale_temperature", "sensor.sv_vesi_maha_temperature",
    )),
  };
  const targetResponse = await fetch(`${baseUrl}/api/states/switch.sonoff_1001208b81_1`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const target = targetResponse.ok ? await targetResponse.json() : null;
  const storedEntriesResponse = await fetch(
    `${ingress}/api/file?filename=${encodeURIComponent("/homeassistant/.storage/core.config_entries")}`,
    { headers: { Authorization: `Bearer ${accessToken}`, Cookie: `ingress_session=${session}` } },
  );
  const storedEntries = JSON.parse(await storedEntriesResponse.text());
  const storedScheduler = storedEntries.data.entries.find(
    (entry) => entry.domain === "smart_energy_scheduler",
  );
  const storedSubentries = await wsRequest({
    type: "config_entries/subentries/list",
    entry_id: storedScheduler.entry_id,
  });
  async function startFlow(path, body) {
    const response = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
        "HA-Frontend-Base": baseUrl,
      },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let result;
    try { result = JSON.parse(text); } catch { result = {}; }
    const summary = {
      status: response.status,
      type: result.type,
      step_id: result.step_id,
      errors: result.errors,
      fields: (result.data_schema || []).map((field) => field.name),
      message: result.message || result.reason || (!response.ok ? text : undefined),
    };
    if (result.flow_id) {
      await fetch(`${baseUrl}${path}/${result.flow_id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
    }
    return summary;
  }
  const reconfigureFlow = await startFlow("/api/config/config_entries/flow", {
    handler: "smart_energy_scheduler",
    entry_id: storedScheduler.entry_id,
  });
  const deviceFlow = await startFlow("/api/config/config_entries/subentries/flow", {
    handler: [storedScheduler.entry_id, "device"],
    subentry_id: storedSubentries[0]?.subentry_id,
  });
  const deviceAddFlow = await startFlow("/api/config/config_entries/subentries/flow", {
    handler: [storedScheduler.entry_id, "device"],
  });
  const errorLogResponse = await fetch(`${baseUrl}/api/error_log`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const relevantLog = (await errorLogResponse.text())
    .split("\n")
    .filter((line) => /smart_energy_scheduler|subentr|config flow/i.test(line))
    .slice(-20);
  const coreLogsResponse = await supervisor("/core/logs").catch(() => "");
  const coreLogText = typeof coreLogsResponse === "string"
    ? coreLogsResponse
    : JSON.stringify(coreLogsResponse);
  const relevantCoreLog = coreLogText
    .split("\n")
    .filter((line) => /smart_energy_scheduler|subentr|config flow|bad request/i.test(line))
    .slice(-30);
  let directWeather = null;
  try {
    const weatherResponse = await wsRequest({
      type: "call_service",
      domain: "weather",
      service: "get_forecasts",
      service_data: { type: "hourly" },
      target: { entity_id: "weather.openweathermap" },
      return_response: true,
    });
    directWeather = {
      entities: Object.keys(weatherResponse.response || weatherResponse || {}),
      forecast_count:
        (weatherResponse.response || weatherResponse)?.["weather.openweathermap"]?.forecast
          ?.length || 0,
    };
  } catch (error) {
    directWeather = { error: error.message };
  }
  const nordpoolDayChecks = [];
  function collectDeliveryStarts(value, result = []) {
    if (Array.isArray(value)) {
      value.forEach((item) => collectDeliveryStarts(item, result));
    } else if (value && typeof value === "object") {
      if (value.deliveryStart || value.start || value.timestamp) {
        result.push(value.deliveryStart || value.start || value.timestamp);
      } else {
        Object.values(value).forEach((item) => collectDeliveryStarts(item, result));
      }
    }
    return result;
  }
  for (const offset of [-1, 0, 1]) {
    const day = new Date();
    day.setDate(day.getDate() + offset);
    const date = day.toLocaleDateString("en-CA", { timeZone: "Europe/Tallinn" });
    try {
      const response = await wsRequest({
        type: "call_service",
        domain: "nordpool",
        service: "hourly",
        service_data: { date, area: ["EE"], currency: "EUR" },
        return_response: true,
      });
      const starts = collectDeliveryStarts(response);
      nordpoolDayChecks.push({
        date,
        ok: true,
        has_response: response?.response != null,
        slots: starts.length,
        first: starts[0],
        last: starts.at(-1),
      });
    } catch (error) {
      nordpoolDayChecks.push({ date, ok: false, error: error.message });
    }
  }
  inspection = {
    ha_version: haConfig.version,
    config_entry_api: schedulerEntries,
    shadow_mode: plan?.shadow_mode,
    plan_hours: plan?.hours?.length || 0,
    temperature_days: Object.keys(plan?.temperatures || {}),
    temperatures: plan?.temperatures || {},
    warnings: plan?.warnings || [],
    configured_weather: storedScheduler?.data?.weather_entity,
    scheduler_config: storedScheduler?.data || {},
    configured_subentries: storedSubentries,
    reconfigure_flow: reconfigureFlow,
    device_reconfigure_flow: deviceFlow,
    device_add_flow: deviceAddFlow,
    relevant_log: relevantLog,
    relevant_core_log: relevantCoreLog,
    devices: Object.keys(plan?.devices || {}).length,
    entities: registry.filter((entity) => entity.config_entry_id === plan?.entry_id).length,
    target_state: target?.state || null,
    target_history_events: targetHistory["switch.sonoff_1001208b81_1"]?.length || 0,
    reasons: Object.values(plan?.devices || {}).map((device) => device.state.reason),
    first_hour: plan?.hours?.[0]?.start || null,
    last_hour: plan?.hours?.at(-1)?.start || null,
    device_plan_valid: Object.values(plan?.devices || {}).map((device) => device.plan?.valid),
    device_plan_error: Object.values(plan?.devices || {}).map((device) => device.plan?.error),
    weather_entities: allStates
      .filter((state) => state.entity_id.startsWith("weather."))
      .map((state) => state.entity_id),
    weather_features: allStates
      .filter((state) => state.entity_id.startsWith("weather."))
      .map((state) => ({ id: state.entity_id, supported_features: state.attributes.supported_features })),
    direct_weather_call: directWeather,
    temperature_candidates: temperatureCandidates,
    pv_power_candidate: allStates.find(
      (state) => state.entity_id === "sensor.a9inverter1_ac_power",
    ) || null,
    scheduler_transition_states: allStates.filter(
      (state) => state.entity_id.includes("next_transition"),
    ),
    control_candidates: controlCandidates,
    temperature_history: temperatureHistorySummary,
    temperature_deltas: temperatureDeltaAnalysis,
    nordpool_day_checks: nordpoolDayChecks,
    first_device_slots: Object.values(plan?.devices || {})[0]?.plan?.hours?.slice(0, 3) || [],
    first_device: Object.values(plan?.devices || {})[0] || null,
    price_hours: plan?.hours || [],
  };
}
if (process.env.HA_RESTART === "1") {
  await Promise.race([
    supervisor("/core/restart", "post", {}).catch(() => null),
    new Promise((resolve) => setTimeout(resolve, 1500)),
  ]);
}
socket.close();
console.log(JSON.stringify({
  uploaded_files: files.length,
  check_config: check.result || check,
  config_flow: configFlow,
  inspection,
  restart_requested: process.env.HA_RESTART === "1",
}));
