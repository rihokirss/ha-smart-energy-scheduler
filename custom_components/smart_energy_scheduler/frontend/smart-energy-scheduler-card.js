class SmartEnergySchedulerCard extends HTMLElement {
  setConfig(config) {
    this.config = { title: "Smart Energy Scheduler", hours: 48, ...config };
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<ha-card><div class="loading">Laadin energiaplaani…</div></ha-card>`;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  async _load() {
    try {
      const response = await this._hass.callWS({
        type: "smart_energy_scheduler/get_plan",
        ...(this.config.entry_id ? { entry_id: this.config.entry_id } : {}),
      });
      this.data = Array.isArray(response) ? response[0] : response;
      if (this._prepareData) await this._prepareData();
      this._render();
      this._unsubscribe = await this._hass.connection.subscribeMessage(
        async (data) => {
          this.data = data;
          if (this._prepareData) await this._prepareData();
          this._render();
        },
        {
          type: "smart_energy_scheduler/subscribe_plan",
          ...(this.config.entry_id ? { entry_id: this.config.entry_id } : {}),
        },
      );
    } catch (err) {
      this.shadowRoot.innerHTML = `<ha-card><div class="error">Plaani laadimine ebaõnnestus: ${this._escape(err.message || err)}</div></ha-card>`;
    }
  }

  disconnectedCallback() {
    if (this._unsubscribe) this._unsubscribe();
  }

  getCardSize() { return 6; }

  static getStubConfig() { return { title: "Smart Energy Scheduler", hours: 48 }; }

  _escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  _color(price, min, max) {
    const ratio = max === min ? 0.5 : Math.max(0, Math.min(1, (price - min) / (max - min)));
    return `hsl(${120 - ratio * 120} 70% 42%)`;
  }

  _useAmPm() {
    const locale = this._hass?.locale || {};
    if (locale.time_format === "12") return true;
    if (locale.time_format === "24") return false;
    const language = locale.time_format === "language" ? locale.language : undefined;
    return new Date("2023-01-01T22:00:00").toLocaleString(language).includes("10");
  }

  _formatTime(date) {
    const locale = this._hass?.locale || {};
    const options = {
      hour: "numeric",
      minute: "2-digit",
      hourCycle: this._useAmPm() ? "h12" : "h23",
    };
    if (locale.time_zone === "server" && this._hass?.config?.time_zone) {
      options.timeZone = this._hass.config.time_zone;
    }
    return new Intl.DateTimeFormat(locale.language, options).format(date);
  }

  _formatDate(date) {
    const locale = this._hass?.locale || {};
    const options = { day: "2-digit", month: "2-digit" };
    if (locale.time_zone === "server" && this._hass?.config?.time_zone) {
      options.timeZone = this._hass.config.time_zone;
    }
    return new Intl.DateTimeFormat(locale.language, options).format(date);
  }

  async _override(deviceId, mode) {
    const data = { device_id: deviceId, mode, entry_id: this.data.entry_id };
    if (mode !== "auto") data.until = new Date(Date.now() + 2 * 3600000).toISOString();
    await this._hass.callService("smart_energy_scheduler", "set_override", data);
  }

  _render() {
    if (!this.data) return;
    const count = Math.max(1, Math.min(48, Number(this.config.hours) || 48));
    const hours = (this.data.hours || []).slice(0, count);
    const prices = hours.map((h) => h.import_eur_mwh);
    const min = Math.min(...prices, 0);
    const max = Math.max(...prices, 1);
    const columns = `repeat(${hours.length || 1}, minmax(18px, 1fr))`;
    const hourCells = hours.map((h) => {
      const date = new Date(h.start);
      const label = this._formatTime(date);
      const title = `${date.toLocaleString()}\nOst ${h.import_eur_mwh.toFixed(1)} €/MWh\nMüük ${h.export_eur_mwh.toFixed(1)} €/MWh\nPV ${(h.pv_wh / 1000).toFixed(2)} kWh`;
      const pv = Math.min(100, h.pv_wh / Math.max(1, ...hours.map((x) => x.pv_wh)) * 100);
      return `<div class="hour" title="${this._escape(title)}">
        <div class="price" style="height:${22 + 30 * ((h.import_eur_mwh - min) / (max - min || 1))}px;background:${this._color(h.import_eur_mwh, min, max)}"></div>
        <div class="pv" style="height:${pv * .28}px"></div><span>${label}</span>
      </div>`;
    }).join("");
    const devices = Object.entries(this.data.devices || {}).map(([id, device]) => {
      const planned = new Map((device.plan?.hours || []).map((h) => [h.start, h]));
      const blocks = hours.map((h) => {
        const slot = planned.get(h.start);
        return `<div class="block ${slot?.active ? "active" : ""}" title="${this._escape(slot?.reason || "off")}"></div>`;
      }).join("");
      const actual = Object.values(device.state.actual_hours_by_day || {}).slice(-1)[0] || 0;
      return `<section class="device">
        <div class="device-head"><div><strong>${this._escape(device.name)}</strong><small>${actual.toFixed(1)} h · ${this._escape(device.state.reason)}</small></div>
        <div class="buttons"><button data-device="${id}" data-mode="auto" class="${device.state.override === "auto" ? "selected" : ""}">Auto</button><button data-device="${id}" data-mode="on" class="${device.state.override === "on" ? "selected" : ""}">ON 2h</button><button data-device="${id}" data-mode="off" class="${device.state.override === "off" ? "selected" : ""}">OFF 2h</button></div></div>
        <div class="blocks" style="grid-template-columns:${columns}">${blocks}</div>
      </section>`;
    }).join("");
    const warnings = (this.data.warnings || []).map((item) => `<li>${this._escape(item)}</li>`).join("");
    this.shadowRoot.innerHTML = `<style>
      :host{display:block} ha-card{padding:16px;overflow:hidden}.top{display:flex;justify-content:space-between;align-items:center;gap:12px}.badge{font-size:12px;padding:4px 8px;border-radius:12px;background:var(--warning-color,#f5a623);color:#111}.badge.live{background:var(--success-color,#43a047);color:#fff}.error{padding:16px;color:var(--error-color,#db4437)}.warnings{font-size:12px;color:var(--secondary-text-color);margin:8px 0}.chart,.blocks{display:grid;gap:2px;min-width:700px}.scroll{overflow-x:auto;padding-bottom:4px}.hour{height:94px;display:flex;flex-direction:column;justify-content:flex-end;align-items:stretch;position:relative}.price{min-height:3px;border-radius:3px 3px 0 0}.pv{background:#fbc02d;min-height:0}.hour span{font-size:9px;white-space:nowrap;transform:rotate(-55deg);transform-origin:top left;margin-top:8px;color:var(--secondary-text-color)}.device{margin-top:16px}.device-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}.device small{display:block;color:var(--secondary-text-color);margin-top:2px}.block{height:22px;border-radius:3px;background:var(--divider-color,#ddd)}.block.active{background:var(--primary-color,#03a9f4)}button{border:1px solid var(--divider-color);background:transparent;color:var(--primary-text-color);padding:5px 8px;cursor:pointer}button.selected{background:var(--primary-color);color:#fff}.legend{font-size:11px;color:var(--secondary-text-color);margin-top:8px}@media(max-width:600px){.device-head{align-items:flex-start;flex-direction:column}}
    </style><ha-card>
      <div class="top"><h2>${this._escape(this.config.title)}</h2><span class="badge ${this.data.shadow_mode ? "" : "live"}">${this.data.shadow_mode ? "VARIREŽIIM" : "JUHTIMINE AKTIIVNE"}</span></div>
      ${this.data.error ? `<div class="error">${this._escape(this.data.error)}</div>` : ""}
      ${warnings ? `<ul class="warnings">${warnings}</ul>` : ""}
      <div class="scroll"><div class="chart" style="grid-template-columns:${columns}">${hourCells}</div>${devices}</div>
      <div class="legend">Tulba värv: ostuhind · kollane: PV prognoos · sinine: seadme töötund</div>
    </ha-card>`;
    this.shadowRoot.querySelectorAll("button[data-mode]").forEach((button) => {
      button.addEventListener("click", () => this._override(button.dataset.device, button.dataset.mode));
    });
  }
}

customElements.define("smart-energy-scheduler-card", SmartEnergySchedulerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-energy-scheduler-card",
  name: "Smart Energy Scheduler",
  description: "48-hour price, solar, and controlled-device plan",
  preview: true,
});

class SmartEnergyPricePlanCard extends SmartEnergySchedulerCard {
  setConfig(config) {
    super.setConfig({ title: "Elektrihind ja seadme tööplaan", hours: 48, ...config });
  }

  _selectedDevice() {
    const entries = Object.entries(this.data?.devices || {});
    return entries.find(([id, device]) =>
      id === this.config.device_id ||
      device.name === this.config.device ||
      device.target_entity === this.config.target_entity
    ) || entries[0];
  }

  async _prepareData() {
    const selected = this._selectedDevice();
    const firstHour = this.data?.hours?.[0]?.start;
    if (!selected || !firstHour) {
      this._history = {};
      return;
    }
    const targetEntity = selected[1].power_sensor || selected[1].feedback_entity || selected[1].target_entity;
    this._historyEntity = targetEntity;
    try {
      this._history = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: new Date(firstHour).toISOString(),
        end_time: new Date().toISOString(),
        entity_ids: [targetEntity],
        minimal_response: true,
        no_attributes: true,
      });
    } catch (_err) {
      this._history = {};
    }
  }

  _actualActivity(hour, device) {
    const start = new Date(hour.start).getTime();
    const end = Math.min(start + 3600000, Date.now());
    if (start >= Date.now()) return null;
    const events = this._history?.[this._historyEntity] || [];
    let state = null;
    let cursor = start;
    let activeMs = 0;
    for (const event of events) {
      const stamp = Number(event.lu ?? event.lc) * 1000 || Date.parse(event.last_changed || "");
      const eventState = event.s ?? event.state;
      if (!Number.isFinite(stamp)) continue;
      if (stamp <= start) {
        state = eventState;
        continue;
      }
      if (stamp >= end) break;
      if (this._historyStateActive(state, device)) activeMs += stamp - cursor;
      cursor = stamp;
      state = eventState;
    }
    if (this._historyStateActive(state, device)) activeMs += Math.max(0, end - cursor);
    return state === null ? null : { active: activeMs > 0, minutes: activeMs / 60000 };
  }

  _historyStateActive(state, device) {
    if (device.power_sensor && this._historyEntity === device.power_sensor) {
      return Number(state) * Number(device.power_multiplier || 1) > 10;
    }
    if (device.feedback_entity && this._historyEntity === device.feedback_entity) {
      return ["on", "open", "opening", "heat", "heating", "active"].includes(state);
    }
    if (state !== "on" && state !== "off") return false;
    return device.inverted ? state === "off" : state === "on";
  }

  _render() {
    if (!this.data) return;
    const selected = this._selectedDevice();
    if (!selected) {
      this.shadowRoot.innerHTML = `<ha-card><div class="error">Ühtegi juhitavat seadet ei ole seadistatud.</div></ha-card>`;
      return;
    }
    const [deviceId, device] = selected;
    const count = Math.max(1, Math.min(48, Number(this.config.hours) || 48));
    const hours = (this.data.hours || []).slice(0, count);
    const planned = new Map((device.plan?.hours || []).map((slot) => [slot.start, slot]));
    const values = hours.flatMap((hour) => {
      const effective = planned.get(hour.start)?.effective_eur_mwh;
      return Number.isFinite(effective) ? [hour.import_eur_mwh, effective] : [hour.import_eur_mwh];
    });
    const minimum = Math.min(0, ...values);
    const maximum = Math.max(1, ...values);
    const width = Math.max(780, hours.length * 34);
    const chartHeight = 280;
    const left = 44, right = 18, top = 32, bottom = 70;
    const plotWidth = width - left - right;
    const plotHeight = chartHeight - top - bottom;
    const step = plotWidth / Math.max(1, hours.length);
    const y = (value) => top + (maximum - value) / (maximum - minimum || 1) * plotHeight;
    const baseline = y(0);
    const now = Date.now();
    const bars = hours.map((hour, index) => {
      const slot = planned.get(hour.start);
      const start = new Date(hour.start).getTime();
      const historical = start + 3600000 <= now;
      const actual = historical ? this._actualActivity(hour, device) : null;
      const active = historical ? Boolean(actual?.active) : Boolean(slot?.active);
      const x = left + index * step + step * .07;
      const barWidth = Math.max(3, step * .86);
      const valueY = y(hour.import_eur_mwh);
      const rectY = Math.min(valueY, baseline);
      const rectHeight = Math.max(1, Math.abs(baseline - valueY));
      const current = start <= now && now < start + 3600000;
      const stroke = current ? (device.state.observed_active ? "#1565c0" : "#616161") : "none";
      const status = historical
        ? (actual?.active ? `Tegelikult ON (${actual.minutes.toFixed(0)} min)` : "Tegelikult OFF")
        : (active ? "Planeeritud ON" : "Planeeritud OFF");
      const fill = historical
        ? (actual?.active ? "#157347" : "#9e9e9e")
        : (active ? "#25a244" : "#f59e0b");
      const tooltip = `${new Date(hour.start).toLocaleString()}\n${status}\nOstuhind ${hour.import_eur_mwh.toFixed(1)} €/MWh\nEfektiivhind ${(slot?.effective_eur_mwh ?? hour.import_eur_mwh).toFixed(1)} €/MWh\nPV ${(hour.pv_wh / 1000).toFixed(2)} kWh`;
      return `<rect x="${x}" y="${rectY}" width="${barWidth}" height="${rectHeight}" rx="2" fill="${fill}" stroke="${stroke}" stroke-width="${current ? 3 : 0}"><title>${this._escape(tooltip)}</title></rect>`;
    }).join("");
    const points = hours.map((hour, index) => {
      const effective = planned.get(hour.start)?.effective_eur_mwh ?? hour.import_eur_mwh;
      return `${left + index * step + step / 2},${y(effective)}`;
    }).join(" ");
    const grid = [0, .25, .5, .75, 1].map((ratio) => {
      const lineY = top + ratio * plotHeight;
      return `<line x1="${left}" y1="${lineY}" x2="${width - right}" y2="${lineY}" stroke="var(--divider-color,#ddd)" stroke-dasharray="3 3"/>`;
    }).join("");
    const yAxisLabels = [0, .25, .5, .75, 1].map((ratio) => {
      const value = maximum - ratio * (maximum - minimum);
      const lineY = top + ratio * plotHeight;
      return `<span style="top:${lineY}px">${value.toFixed(0)}</span>`;
    }).join("");
    const labels = hours.map((hour, index) => {
      const stamp = new Date(hour.start);
      const hourLabel = this._formatTime(stamp);
      const dateLabel = this._formatDate(stamp);
      const x = left + index * step + step / 2;
      const showDate = index === 0 || this._formatDate(new Date(hours[index - 1].start)) !== dateLabel;
      return `${showDate ? `<line x1="${left + index * step}" y1="${top}" x2="${left + index * step}" y2="${baseline + 7}" stroke="var(--secondary-text-color)" opacity=".45"/><text class="date" x="${x}" y="${top - 10}" text-anchor="middle">${dateLabel}</text>` : ""}<text class="hour-label" x="${x}" y="${baseline + 24}" text-anchor="middle" transform="rotate(-45 ${x} ${baseline + 24})">${hourLabel}</text>`;
    }).join("");
    const stateText = device.state.observed_active === true ? "praegu sees" : device.state.observed_active === false ? "praegu väljas" : "tegelik olek teadmata";
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{padding:16px;overflow:hidden}.head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.head h2{margin:0 0 4px}.sub{color:var(--secondary-text-color);font-size:13px}.chart-wrap{position:relative;margin-top:12px}.scroll{overflow-x:auto;scrollbar-gutter:stable;padding-bottom:4px}svg{display:block;height:auto;max-width:none}svg text{font:12px sans-serif;fill:var(--secondary-text-color)}svg .hour-label{font-size:13px;font-weight:500;fill:var(--primary-text-color)}svg .date{font-size:13px;font-weight:700;fill:var(--primary-text-color)}.y-axis{position:absolute;z-index:2;left:0;top:0;width:40px;height:${chartHeight}px;pointer-events:none;background:var(--ha-card-background,var(--card-background-color,#fff));box-shadow:3px 0 5px -5px var(--primary-text-color)}.y-axis span{position:absolute;right:4px;transform:translateY(-50%);font-size:11px;font-weight:600;color:var(--secondary-text-color)}.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin-top:10px;color:var(--secondary-text-color)}.key{display:inline-flex;gap:5px;align-items:center}.swatch{width:12px;height:12px;border-radius:2px}.line{width:20px;border-top:3px solid #2196f3}.badge{font-size:11px;padding:4px 8px;border-radius:10px;background:var(--warning-color,#f5a623);color:#111}.badge.live{background:var(--success-color,#43a047);color:white}.error{padding:16px;color:var(--error-color,#db4437)}
    </style><ha-card>
      <div class="head"><div><h2>${this._escape(this.config.title)}</h2><div class="sub">${this._escape(device.name)} · ${stateText} · ${this._escape(device.state.reason)}</div></div><span class="badge ${this.data.shadow_mode ? "" : "live"}">${this.data.shadow_mode ? "VARIREŽIIM" : "AKTIIVNE"}</span></div>
      ${this.data.error ? `<div class="error">${this._escape(this.data.error)}</div>` : ""}
      <div class="chart-wrap"><div class="y-axis" aria-label="Hinnaskaala eurot megavatt-tunni kohta">${yAxisLabels}</div><div class="scroll"><svg style="width:${width}px" viewBox="0 0 ${width} ${chartHeight}" role="img" aria-label="Elektrihinna ja seadme tööplaani graafik">${grid}<line x1="${left}" y1="${baseline}" x2="${width - right}" y2="${baseline}" stroke="var(--primary-text-color)"/>${bars}<polyline points="${points}" fill="none" stroke="#2196f3" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>${labels}</svg></div></div>
      <div class="legend"><span class="key"><i class="swatch" style="background:#157347"></i>tegelikult ON</span><span class="key"><i class="swatch" style="background:#9e9e9e"></i>möödunud OFF</span><span class="key"><i class="swatch" style="background:#25a244"></i>planeeritud ON</span><span class="key"><i class="swatch" style="background:#f59e0b"></i>planeeritud OFF</span><span class="key"><i class="line"></i>efektiivhind koos PV-ga</span><span>tulba kõrgus: ostuhind €/MWh</span></div>
    </ha-card>`;
    if (!this._initialScrollDone) {
      requestAnimationFrame(() => {
        const scroll = this.shadowRoot.querySelector(".scroll");
        const currentIndex = hours.findIndex((hour) => {
          const start = new Date(hour.start).getTime();
          return start <= now && now < start + 3600000;
        });
        if (scroll && currentIndex >= 0) {
          const currentX = left + currentIndex * step + step / 2;
          scroll.scrollLeft = Math.max(0, currentX - scroll.clientWidth / 2);
        }
        this._initialScrollDone = true;
      });
    }
  }
}

customElements.define("smart-energy-price-plan-card", SmartEnergyPricePlanCard);
window.customCards.push({
  type: "smart-energy-price-plan-card",
  name: "Smart Energy Price & Device Plan",
  description: "Price bars colored by planned device activity",
  preview: true,
});
