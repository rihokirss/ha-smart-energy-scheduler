#!/usr/bin/env node
/** Inspect or add the price-plan card to a storage-mode Lovelace dashboard. */

const baseUrl = (process.env.HA_URL || "http://192.168.0.200:8123").replace(/\/$/, "");
const clientId = process.env.HA_CLIENT_ID || "http://localhost/";
const username = process.env.HA_USER;
const password = process.env.HA_PASSWORD;
const urlPath = process.env.HA_DASHBOARD || "lovelace-ipad";
const viewPath = process.env.HA_VIEW || "ekraan";
const mode = process.env.MODE || "inspect";
if (!username || !password) throw new Error("Set HA_USER and HA_PASSWORD");

const flowResponse = await fetch(`${baseUrl}/auth/login_flow`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ client_id: clientId, handler: ["homeassistant", null], redirect_uri: clientId }),
});
const flow = await flowResponse.json();
const loginResponse = await fetch(`${baseUrl}/auth/login_flow/${flow.flow_id}`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ client_id: clientId, username, password }),
});
const login = await loginResponse.json();
if (!login.result) throw new Error("HA login failed");
const tokenResponse = await fetch(`${baseUrl}/auth/token`, {
  method: "POST",
  headers: { "Content-Type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams({ grant_type: "authorization_code", code: login.result, client_id: clientId }),
});
const { access_token: accessToken } = await tokenResponse.json();

const socket = new WebSocket(`${baseUrl.replace(/^http/, "ws")}/api/websocket`);
let nextId = 1;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "auth_required") socket.send(JSON.stringify({ type: "auth", access_token: accessToken }));
  else if (message.type === "result" && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    message.success ? resolve(message.result) : reject(new Error(JSON.stringify(message.error)));
  }
});
await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error("HA WebSocket timeout")), 10000);
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "auth_ok") { clearTimeout(timeout); resolve(); }
    if (message.type === "auth_invalid") { clearTimeout(timeout); reject(new Error("HA WebSocket auth failed")); }
  });
});
function call(payload) {
  const id = nextId++;
  socket.send(JSON.stringify({ id, ...payload }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

const config = await call({ type: "lovelace/config", url_path: urlPath, force: true });
const view = config.views?.find((candidate) => candidate.path === viewPath);
if (!view) throw new Error(`View ${viewPath} not found in ${urlPath}`);
const summary = {
  dashboard: urlPath,
  view: { title: view.title, path: view.path, type: view.type || "masonry" },
  cards: (view.cards || []).map((card) => ({ type: card.type, title: card.title })),
  sections: (view.sections || []).map((section) => ({
    type: section.type,
    cards: (section.cards || []).map((card) => ({ type: card.type, title: card.title })),
  })),
};

if (mode === "title") {
  const priceCards = [];
  for (const card of view.cards || []) {
    if (card.type === "custom:smart-energy-price-plan-card") priceCards.push(card);
  }
  for (const section of view.sections || []) {
    for (const card of section.cards || []) {
      if (card.type === "custom:smart-energy-price-plan-card") priceCards.push(card);
    }
  }
  let changed = false;
  for (const card of priceCards) {
    if (card.title !== "Hind ja tööplaan") {
      card.title = "Hind ja tööplaan";
      changed = true;
    }
  }
  if (changed) await call({ type: "lovelace/config/save", url_path: urlPath, config });
  summary.title_updated = changed;
  summary.price_cards = priceCards.length;
}

if (mode === "add" || mode === "resource") {
  const resourceUrl = "/smart_energy_scheduler/smart-energy-scheduler-card.js";
  const versionedResourceUrl = `${resourceUrl}?v=0.8.13`;
  const resources = await call({ type: "lovelace/resources/list" });
  const existingResource = resources.find((resource) => resource.url.split("?")[0] === resourceUrl);
  if (!existingResource) {
    await call({ type: "lovelace/resources/create", res_type: "module", url: versionedResourceUrl });
  } else if (existingResource.url !== versionedResourceUrl) {
    await call({
      type: "lovelace/resources/update",
      resource_id: existingResource.id,
      res_type: "module",
      url: versionedResourceUrl,
    });
  }
  if (mode === "resource") {
    summary.resource_updated = true;
    socket.close();
    console.log(JSON.stringify(summary));
    process.exit(0);
  }
  const priceCard = {
    type: "custom:smart-energy-price-plan-card",
    title: "Hind ja tööplaan",
    target_entity: "switch.sonoff_1001208b81_1",
    hours: 48,
  };
  const curveCard = {
    type: "custom:smart-energy-heating-curve-card",
    title: "Soojuspumba küttekõver",
    target_entity: "switch.sonoff_1001208b81_1",
  };
  const serialized = JSON.stringify(view);
  let changed = false;
  if (!serialized.includes("custom:smart-energy-price-plan-card")) {
    if (Array.isArray(view.sections)) {
      const priceSection = view.sections.find((section) =>
        (section.cards || []).some((existing) => existing.type === "custom:apexcharts-card")
      );
      if (priceSection) priceSection.cards.push(priceCard);
      else view.sections.push({ type: "grid", cards: [priceCard] });
    } else {
      view.cards = [...(view.cards || []), priceCard];
    }
    changed = true;
  }
  if (!serialized.includes("custom:smart-energy-heating-curve-card")) {
    if (Array.isArray(view.sections)) view.sections.push({ type: "grid", cards: [curveCard] });
    else view.cards = [...(view.cards || []), curveCard];
    changed = true;
  }
  if (changed) await call({ type: "lovelace/config/save", url_path: urlPath, config });
  summary.added = changed;
}

socket.close();
console.log(JSON.stringify(summary));
